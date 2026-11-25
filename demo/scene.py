"""The demo scene in one place: who is where, which files, which words.

Everything here is invented: the person, the visa number (it starts with
999000), the hotels. The pages, the replay and the scenario card all read the
scene from here, so they cannot drift apart.
"""

from pathlib import Path

SCENE_DIR = Path(__file__).resolve().parent / "scene"

# The counter this scene is sent from. The pilgrim's own hotel is a different one.
REPORTING_HOTEL = "برج السكينة"

COUNTER_FILE = "01_counter_arabic.wav"
COUNTER_NOTE = (
    "السلام عليكم، معكم الاستقبال. عندنا حاج كبير في السن واقف عند الاستقبال، تايه وما يعرف فندقه، "
    "ما يتكلم عربي، يتكلم أردو بس، وما هو من حجاج شركتنا."
)
PILGRIM_FILE = "02_pilgrim_urdu.wav"
PILGRIM_NOTE = (
    "السلام علیکم، میرا نام زاہد کریم ہے۔ میں راستہ بھول گیا ہوں، مجھے اپنے ہوٹل کا نام یاد نہیں۔ "
    "میں اکیلا ہوں، میری مدد کریں۔"
)

# What the pilgrim's note means, for the people in the hall who do not read Urdu.
PILGRIM_NOTE_MEANING = "السلام عليكم، اسمي زاهد كريم. ضللت الطريق ولا أتذكر اسم فندقي. أنا وحدي، ساعدوني."

# What is printed on the mock card. The holder is one of the invented people in data/simulated_elm.json.
CARD_FILE = "mock_card.png"
CARD_NAME = "ZAHID KARIM"
CARD_VISA = "9990007788"
CARD_MARKS = ("SPECIMEN", "نموذج تجريبي")
