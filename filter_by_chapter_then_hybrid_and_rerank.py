import os
import re
from typing import Dict, List, Tuple

import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.query import MetadataQuery, Filter
from dotenv import load_dotenv

try:
    import cohere
except ImportError:
    cohere = None

load_dotenv()

WEAVIATE_CLUSTER = os.getenv("WEAVIATE_CLUSTER")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
HF_API_KEY = os.getenv("HF_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "ClinicalRAG")

QUERY = """Kawasaki disease diagnostic criteria fever duration 5 days clinical diagnosis rules,
Kawasaki disease diagnosis criteria mucocutaneous lymph node syndrome diagnostic features,
Kawasaki disease incomplete atypical diagnosis infants criteria and evaluation,
diagnosis of Kawasaki disease coronary artery involvement echocardiography criteria,
Kawasaki disease diagnostic approach clinical criteria laboratory findings CRP ESR platelets,
clinical diagnosis of Kawasaki disease fever rash conjunctivitis oral changes extremity changes lymphadenopathy criteria,
differential diagnosis of Kawasaki disease scarlet fever toxic shock syndrome viral exanthems,
Kawasaki disease evaluation diagnosis criteria and confirmation guidelines
"""

K = 250
ALPHA = 0.35
TOP_N = 15
USE_RERANK = True

TARGET_CHAPTER_NUMBER = "249"
TARGET_DISEASE = "Kawasaki disease"


# ---------------- INTENT ----------------
INTENT_TO_SUBSECTION = {
    "treatment": {"treatment"},
    "diagnosis": {"diagnosis", "clinical_manifestations"},
    "investigation": {"diagnosis"},
    "prognosis": {"prognosis"},
    "general": set(),
}


def detect_intent(query: str) -> str:
    q = query.lower()
    if any(x in q for x in ["treatment", "management", "medication", "therapy", "drug", "inhaled"]):
        return "treatment"
    if any(x in q for x in ["diagnosis", "features", "criteria"]):
        return "diagnosis"
    return "general"


def detect_primary_disease(query: str) -> str:
    diseases = [
        "dengue", "pneumonia", "meningitis", "diabetes",
        "tuberculosis", "kawasaki", "asthma", "sepsis"
    ]
    q = query.lower()
    for d in diseases:
        if d in q:
            return d
    return ""


# ---------------- FILTER ----------------
def build_asthma_chapter_filter():
    """
    Restrict retrieval to:
    - Chapter 75
    OR
    - disease_name == asthma
    OR
    - chapter_title contains asthma
    """
    return (
        Filter.by_property("chapter_number").equal(TARGET_CHAPTER_NUMBER)
        |
        Filter.by_property("disease_name").like("*asthma*")
        |
        Filter.by_property("chapter_title").like("*asthma*")
    )


# ---------------- HYBRID ----------------
def hybrid_retrieve_with_scores(collection, query, k=50, alpha=0.5):
    scoped_filter = build_asthma_chapter_filter()

    response = collection.query.hybrid(
        query=query,
        alpha=alpha,
        limit=k,
        filters=scoped_filter,
        return_metadata=MetadataQuery(score=True),
    )

    results = []
    for obj in response.objects:
        props = obj.properties or {}

        results.append({
            "content": props.get("content", ""),
            "book_title": props.get("book_title", ""),
            "part_title": props.get("part_title", ""),
            "section_title": props.get("section_title", ""),
            "chapter_number": props.get("chapter_number", ""),
            "chapter_title": props.get("chapter_title", ""),
            "subsection_title": props.get("subsection_title", ""),
            "normalized_subsection": props.get("normalized_subsection", ""),
            "hierarchy_path": props.get("hierarchy_path", ""),
            "page_start": props.get("page_start"),
            "page_end": props.get("page_end"),
            "content_type": props.get("content_type", ""),
            "specialty": props.get("specialty", ""),
            "age_group": props.get("age_group", ""),
            "disease_name": props.get("disease_name", ""),
            "score": getattr(obj.metadata, "score", 0),
        })

    return results


# ---------------- CLEAN ----------------
def post_filter_results(results: List[Dict]) -> List[Dict]:
    cleaned = []
    seen = set()

    for r in results:
        key = (
            r.get("chapter_number"),
            r.get("chapter_title"),
            r.get("subsection_title"),
            (r.get("content") or "")[:150]
        )

        if key in seen:
            continue
        seen.add(key)

        if not r["content"].strip():
            continue

        cleaned.append(r)

    return cleaned


# ---------------- DISEASE DOMINANCE ----------------
def enforce_disease_priority(results, disease_term, top_k=20):
    if not disease_term:
        return results

    strong = []
    others = []

    for r in results:
        text = " ".join([
            r.get("disease_name", ""),
            r.get("chapter_title", ""),
            r.get("subsection_title", ""),
            r.get("content", "")[:1000]
        ]).lower()

        if disease_term in text:
            strong.append(r)
        else:
            others.append(r)

    final = strong[:top_k]

    if len(final) < top_k:
        final += others[:(top_k - len(final))]

    return final


# ---------------- SCORING ----------------
def preference_score(item, disease_term, intent):
    subsection = item.get("subsection_title", "").lower()
    norm_sub = item.get("normalized_subsection", "").lower()
    chapter = item.get("chapter_title", "").lower()
    disease_name = item.get("disease_name", "").lower()
    content = item.get("content", "").lower()[:1500]
    chapter_number = str(item.get("chapter_number", "")).lower()

    disease_score = (
        5 * int(disease_term in disease_name) +
        4 * int(disease_term in chapter) +
        2 * int(disease_term in subsection) +
        1 * int(disease_term in content)
    )

    chapter_score = 3 * int(chapter_number == TARGET_CHAPTER_NUMBER)

    # medication-heavy treatment preference
    medication_terms = [
        "medication", "drug", "inhaled", "corticosteroid", "bronchodilator",
        "beta agonist", "saba", "laba", "controller", "reliever", "leukotriene"
    ]
    medication_score = sum(term in content for term in medication_terms)

    allowed = INTENT_TO_SUBSECTION.get(intent, set())
    subsection_score = int(norm_sub in allowed)

    hybrid_score = item.get("score", 0)

    return (
        chapter_score,
        disease_score,
        subsection_score,
        medication_score,
        hybrid_score
    )


def sort_results(results, disease_term, intent):
    return sorted(
        results,
        key=lambda x: preference_score(x, disease_term, intent),
        reverse=True
    )


# ---------------- RERANK ----------------
def rerank_results(query, results, top_n=5):
    if not COHERE_API_KEY or cohere is None:
        fallback = results[:top_n]
        for r in fallback:
            r["rerank_score"] = None
        return fallback

    client = cohere.Client(COHERE_API_KEY)

    docs = []
    for r in results:
        docs.append(
            f"""
Book: {r.get('book_title')}
Part: {r.get('part_title')}
Section: {r.get('section_title')}
Chapter: {r.get('chapter_number')} - {r.get('chapter_title')}
Subsection: {r.get('subsection_title')}
Normalized Subsection: {r.get('normalized_subsection')}
Disease: {r.get('disease_name')}
Pages: {r.get('page_start')} - {r.get('page_end')}

{r.get('content')}
"""
        )

    rerank = client.rerank(
        query=query,
        documents=docs,
        top_n=top_n,
        model="rerank-english-v3.0"
    )

    reranked_results = []
    for rr in rerank.results:
        item = dict(results[rr.index])  # copy original result
        item["rerank_score"] = rr.relevance_score
        reranked_results.append(item)

    return reranked_results

# ---------------- PRINT ----------------
def print_results(results):
    print("\n===== FINAL RESULTS =====")

    for i, r in enumerate(results, 1):
        print("\n" + "=" * 80)
        print(f"Rank {i}")
        print(f"Book: {r.get('book_title')}")
        print(f"Part: {r.get('part_title')}")
        print(f"Section: {r.get('section_title')}")
        print(f"Chapter: {r.get('chapter_number')} - {r.get('chapter_title')}")
        print(f"Subsection: {r.get('subsection_title')}")
        print(f"Normalized Subsection: {r.get('normalized_subsection')}")
        print(f"Hierarchy: {r.get('hierarchy_path')}")
        print(f"Pages: {r.get('page_start')} - {r.get('page_end')}")
        print(f"Content Type: {r.get('content_type')}")
        print(f"Specialty: {r.get('specialty')} | Age: {r.get('age_group')}")
        print(f"Disease Tag: {r.get('disease_name')}")
        print(f"Hybrid Score: {r.get('score')}")
        print(f"Rerank Score: {r.get('rerank_score')}")
        print("-" * 80)
        print(r.get("content", ""))


# ---------------- MAIN ----------------
def main():
    query = QUERY.strip()

    intent = detect_intent(query)
    disease = detect_primary_disease(query)

    print("Intent:", intent)
    print("Disease:", disease)
    print("Target Chapter:", TARGET_CHAPTER_NUMBER)
    print("Alpha:", ALPHA)

    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=WEAVIATE_CLUSTER,
        auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
        headers={"X-HuggingFace-Api-Key": HF_API_KEY},
    )

    try:
        collection = client.collections.get(COLLECTION_NAME)

        # first hit only asthma / chapter 75 scoped results
        results = hybrid_retrieve_with_scores(collection, query, K, ALPHA)
        print("Raw:", len(results))

        results = post_filter_results(results)
        print("Filtered:", len(results))

        results = sort_results(results, disease, intent)

        # disease dominance after sorting
        results = enforce_disease_priority(results, disease)

        if USE_RERANK:
            results = rerank_results(query, results, TOP_N)
        else:
            results = results[:TOP_N]

        print_results(results)

    finally:
        client.close()


if __name__ == "__main__":
    main()