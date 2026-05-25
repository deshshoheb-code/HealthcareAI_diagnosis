from main import run_pipeline
from chapter_findings import get_chapter_matches
from filter_by_rag_2 import main as rag_search


def build_query(disease: str, intent: str = "diagnosis"):
    """
    Simple dynamic query builder.
    You can later make this more advanced.
    """

    if intent == "diagnosis":
        return f"""
        {disease} symptoms signs clinical features diagnosis criteria,
        {disease} diagnostic approach history examination evaluation,
        {disease} differential diagnosis and clinical findings
        """

    elif intent == "treatment":
        return f"""
        {disease} treatment management medications therapy protocol,
        {disease} first line treatment and supportive care
        """

    else:
        return disease


def orchestrate():
    # ---------------- STEP 1: RUN PIPELINE ----------------
    pipeline_output = run_pipeline()

    provisional = pipeline_output["provisional_diagnosis"]

    primary = provisional.primary_diagnosis
    alt1 = provisional.alternative_diagnosis_1
    alt2 = provisional.alternative_diagnosis_2

    print("\n===== DIAGNOSES =====")
    print("Primary:", primary)
    print("Alt1:", alt1)
    print("Alt2:", alt2)

    # ---------------- STEP 2: GET CHAPTER MATCHES ----------------
    chapter_matches = get_chapter_matches(primary, alt1, alt2)

    primary_chapters = [
        str(x["chapter_number"])
        for x in chapter_matches["primary_disease"]
        if x["chapter_number"] is not None
    ]

    alt1_chapters = [
        str(x["chapter_number"])
        for x in chapter_matches["alternative_disease_1"]
        if x["chapter_number"] is not None
    ]

    alt2_chapters = [
        str(x["chapter_number"])
        for x in chapter_matches["alternative_disease_2"]
        if x["chapter_number"] is not None
    ]

    print("\n===== CHAPTERS =====")
    print("Primary Chapters:", primary_chapters)
    print("Alt1 Chapters:", alt1_chapters)
    print("Alt2 Chapters:", alt2_chapters)

    # ---------------- STEP 3: BUILD QUERIES ----------------
    primary_query = build_query(primary, "diagnosis")
    alt1_query = build_query(alt1, "diagnosis")
    alt2_query = build_query(alt2, "diagnosis")

    # ---------------- STEP 4: RAG SEARCH ----------------
    print("\n===== RAG: PRIMARY =====")
    primary_results = rag_search(
        query=primary_query,
        target_chapter_numbers=primary_chapters,
        disease_term=primary
    )

    print("\n===== RAG: ALT 1 =====")
    alt1_results = rag_search(
        query=alt1_query,
        target_chapter_numbers=alt1_chapters,
        disease_term=alt1
    )

    print("\n===== RAG: ALT 2 =====")
    alt2_results = rag_search(
        query=alt2_query,
        target_chapter_numbers=alt2_chapters,
        disease_term=alt2
    )

    return {
        "primary_results": primary_results,
        "alt1_results": alt1_results,
        "alt2_results": alt2_results,
    }


if __name__ == "__main__":
    orchestrate()