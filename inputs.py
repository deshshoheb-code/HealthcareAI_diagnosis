# ─────────────────────────────────────────────
# inputs.py
# Hardcoded test inputs for Stage 1 pipeline.
# Replace these with frontend/API inputs when integrating.
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# STAGE 1 INPUT: Raw clinical notes (free text)
# ─────────────────────────────────────────────

chief_complain = '''
History of present illness:

According to the statement of informant (mother), her son was reasonably well 06 days back then he developed episodes of breathing difficulty which were gradual in onset and progressively worsening.

Initially the child developed dry cough which was more prominent at night and early morning. The cough was not associated with sputum production, hemoptysis, or post-tussive vomiting.

After 2 days, he started experiencing shortness of breath which was episodic in nature, associated with a whistling sound during breathing and a feeling of chest tightness. These episodes were more severe during night time and early morning hours and were aggravated by exposure to dust while playing outdoors.

There was partial relief after using previously prescribed inhalational medication at home.

There is history of similar episodes in the past for last 1 year, especially during seasonal changes, which improved with medication but never required hospitalization.

There is no history of fever, chills, rigor, chest pain, orthopnea, paroxysmal nocturnal dyspnea, cyanosis, or syncope.

No history of foreign body aspiration, recent travel, or contact with sick persons.

No history of tuberculosis contact.

Mother also complained of reduced activity and mild irritability during episodes.

His bowel and bladder habits are normal.

With these complaints, they consulted a local physician and were given oral medications but as symptoms persisted, he was brought for further evaluation.

On General Examination:

Appearance: mildly distressed during breathing, conscious and oriented.
Pallor           : Absent
Jaundice      : Absent
Cyanosis      : Absent at rest
Clubbing      : Absent
Koilonychia : Absent
Leukonychia: Absent
Oedema       : Absent
Dehydration: Absent

Lip                 : Normal
Tongue         : Moist
Eyes              : Normal
Lymph node: Not enlarged
BCG mark    : Present

Ear, nose                                   : Normal
Throat, oral cavity                   : Normal
Bony tenderness                     : Absent
Signs of meningeal irritation : Absent
Bed side urine for albumin    : Nil

Vital Signs:
Temperature: 98.4°F
BP                   : 100/60 mmHg
Pulse              : 112 bpm
R/R                 : 34 breaths/min
SPO2              : 95% in room air

Anthropometry:
Weight: 22 kg
Height: 125 cm
BMI: within normal limit

'''


# ─────────────────────────────────────────────
# STAGE 3a INPUT: Raw systemic examination text
# ─────────────────────────────────────────────

systemic_examination_result = """
Systemic Examination

Respiratory System
- Respiratory Rate: 34 breaths/min

Inspection:
- Chest movement: Bilaterally reduced
- Use of accessory muscles: Present (intercostal and subcostal retractions)
- Shape of chest: Normal
- Trachea: Central

Palpation:
- Chest expansion: Reduced bilaterally
- Tactile vocal fremitus: Normal

Percussion:
- Note: Hyper-resonant over both lung fields

Auscultation:
- Breath sounds: Vesicular with prolonged expiratory phase
- Added sounds:
  - Bilateral diffuse expiratory wheeze present
- No crepitations

Cardiovascular System
- Heart Rate: 112 beats/min
- Blood Pressure: 100/60 mmHg

Precordium:
- Inspection: No visible pulsation
- Palpation:
  - Apex beat: Left 5th ICS, medial to mid-clavicular line
  - No heave or thrill
- Auscultation:
  - Heart sounds: S1 and S2 normal
  - No added sounds or murmur

Alimentary System
- Abdomen:
  - Inspection: Normal
  - Palpation: Non-tender
  - Liver: Not palpable
  - Spleen: Not palpable
- Bowel sounds: Present

Central Nervous System
- Consciousness: Alert
- Orientation: Normal
- Motor and sensory system: Normal

Other Systems
- No abnormalities detected.
"""
