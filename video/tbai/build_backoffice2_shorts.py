"""Build 2 HeyGen-mode short specs from the backoffice2 long-form's cached beat VOs (reuses the
same ElevenLabs BLEND voice + wording, no new synthesis)."""
import importlib.util, json, pathlib, re, sys
HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(pathlib.Path(r"C:\Users\you\.claude\skills\geo-flywheel\references\engine")))
import short_engine

CACHE = HERE / "build/backoffice2"
SRC = pathlib.Path("vid_backoffice2.py")
text = (HERE / "vid_backoffice2.py").read_text(encoding="utf-8")
vos = re.findall(r'"vo": "((?:[^"\\]|\\.)*)"', text)

beats = [{"text": v, "vo_mp3": str(CACHE / f"beat_{i:03d}.mp3")} for i, v in enumerate(vos)]

WINDOWS = [
    {"start": 0.0, "end": 32.0, "title": "The direct answer + the numbers", "hook": "What AI back office actually works for a ServiceTitan shop?"},
    {"start": 316.0, "end": 351.0, "title": "Is this just another chatbot?", "hook": "Fair question: is this just another chatbot?"},
]

OUT_DIR = HERE / "build/shorts_backoffice2"; OUT_DIR.mkdir(parents=True, exist_ok=True)

for n, m in enumerate(WINDOWS, start=1):
    spec = short_engine.build_spec_from_beats(
        beats, m, "top-builder-ai",
        out_dir=str(OUT_DIR),
        cluster="ai-back-office-servicetitan",
        source_id="fd83471877af9458",
        cycle="2026-07-18",
    )
    spec_path = OUT_DIR / f"spec_{n}.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"SPEC {n} -> {spec_path} | script: {spec['script'][:90]}... | audio: {spec['audio_mp3']}")
