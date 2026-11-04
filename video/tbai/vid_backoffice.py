"""'AI back office for ServiceTitan' video BODY — mirrors /blog/ai-back-office-for-servicetitan.html."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py")); ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)
IMG = str(HERE / "build/img/backoffice") + "/"
CACHE = HERE / "build/backoffice"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/backoffice_body.mp4"
def P(n): return IMG + n + ".jpg"

B = [
  {"vo": "ServiceTitan is great at the front office. The calls, the schedule, the dispatch board, the invoice — that's the part it was built for, and it even has its own AI agents there now.",
   "scene": "split_photo", "c": {"photo": P("frontoffice"), "eyebrow": "The front office", "title": "ServiceTitan runs this well", "sub": "Calls · schedule · dispatch · invoicing"}},
  {"vo": "But there's a whole other half of your business it never automated. The back office — the money, the materials, the people, the paperwork, your receivables, and your pricebook.",
   "scene": "split_photo", "c": {"photo": P("backoffice_pile"), "eyebrow": "The other half", "title": "The back office it never built", "sub": "Money · Materials · People · Paperwork · A/R · Pricebook"}},
  {"vo": "And that's where the margin quietly leaks. Cash you can't see coming, materials nobody costed, overtime nobody caught, invoices nobody chased — most of it still done by hand.",
   "scene": "split_photo", "c": {"photo": P("margin_leak"), "eyebrow": "Where margin leaks", "title": "Done by hand, after hours", "sub": "And nobody can trace the leak"}},

  {"vo": "So here's the idea.", "scene": "chapter", "c": {"num": "01", "title": "An AI back office for ServiceTitan"}},
  {"vo": "Self-learning AI agents that install on the ServiceTitan you already run, and handle that back-office work — turning your data into deterministic, audited recommendations you approve.",
   "scene": "define", "c": {"eyebrow": "The idea", "term": "An AI back office", "body": "Self-learning agents on the ServiceTitan you already run — your data turned into audited, human-approved actions"}},

  {"vo": "There are eight of them.", "scene": "chapter", "c": {"num": "02", "title": "Two it can't beat. Six it doesn't have."}},
  {"vo": "Two go head to head with ServiceTitan's own agents and win, because ours learn your shop every week: a booking agent that answers and values every call, even after hours, and a dispatcher that routes by drive time, margin, and overtime.",
   "scene": "photo_overlay", "c": {"photo": P("frontoffice"), "overlay": "incoming", "label": "New call — after hours", "sub": "answered, qualified, booked"}},
  {"vo": "Then six run the back office ServiceTitan never touched. Financial projects your cash and flags margin leaks. Inventory catches unbilled materials. Workforce forecasts overtime before it happens. Documents files every form.",
   "scene": "cards", "c": {"title": "The back office, finally automated", "items": [("\U0001F4B5", "Financial"), ("\U0001F4E6", "Inventory"), ("\U0001F477", "Workforce"), ("\U0001F4C4", "Documents")]}},
  {"vo": "And the two newest. Collections works your aging receivables around the clock and drafts every dunning message. Pricebook keeps your material costs current as vendors raise prices, and re-prices the book.",
   "scene": "cards", "c": {"title": "...and the two newest agents", "items": [("\U0001F4CA", "Collections"), ("\U0001F3F7️", "Pricebook")]}},

  {"vo": "Now, why one platform instead of ten apps?", "scene": "chapter", "c": {"num": "03", "title": "Why one brain beats ten tools"}},
  {"vo": "You could buy a separate tool for each of these. One for calls, one for reviews, one for collections. But none of them see your whole shop, and none of them learn how you actually run it.",
   "scene": "split_photo", "c": {"photo": P("bolton_mess"), "eyebrow": "The bolt-on trap", "title": "Ten tools, ten silos", "sub": "None see the whole business"}},
  {"vo": "These agents share one brain. The dispatcher knows what the financial agent knows. And they get smarter every week from what you approve — so they sound more like your business every month, not less.",
   "scene": "split_photo", "c": {"photo": P("command_center"), "eyebrow": "One cross-agent brain", "title": "They see the whole shop", "sub": "And learn your operation weekly"}},

  {"vo": "Which is the real difference from ServiceTitan's own AI.", "scene": "chapter", "c": {"num": "04", "title": "vs. ServiceTitan's own AI agents"}},
  {"vo": "ServiceTitan's agents are frozen — the same output on day three hundred as day one — and siloed in one module. Bolt-on tools are siloed too. Ours learn, and they see the business end to end.",
   "scene": "compare", "c": {"title": "The difference", "cols": ["ServiceTitan AI", "Bolt-on tools", "Top Builder AI"],
     "rows": [("Self-learning every week", [False, False, True]), ("Sees the whole business", [False, False, True]),
              ("Tuned to your shop", [False, False, True]), ("Runs the back office", [False, True, True])]}},

  {"vo": "Because it's your money and your customers, it's built to be safe.", "scene": "chapter", "c": {"num": "05", "title": "Safe by design"}},
  {"vo": "Advisory by default. Every agent proposes, you approve. Everything's reversible with an audit trail. And every number comes from deterministic, tested code — never from a guess.",
   "scene": "secure", "c": {"title": "How it stays safe", "items": [("✅", "Advisory by default", "Every agent proposes; you approve"),
     ("↩", "Reversible", "Every action has an undo + audit trail"), ("🔒", "Deterministic", "Tested code computes every figure — the AI never invents one")]}},

  {"vo": "So here's what actually changes.", "scene": "chapter", "c": {"num": "06", "title": "What changes"}},
  {"vo": "You go from a back office you're holding together by hand and late nights, to one that runs itself in the background — and tells you the moment something needs you.",
   "scene": "before_after", "c": {"before": P("before_stress"), "after": P("after_calm"), "caption": "A back office done by hand → one that runs itself"}},
  {"vo": "Your front office stays exactly where it is, on ServiceTitan. The back office finally has agents of its own.",
   "scene": "split_photo", "c": {"photo": P("handshake"), "eyebrow": "The outcome", "title": "Keep ServiceTitan. Add the back office.", "sub": "We complement it — never replace it"}},
  {"vo": "If ServiceTitan runs your front office but your back office still runs on you, that's exactly what we fix. Read the full breakdown on the blog, then book a call.",
   "scene": "cta", "c": {"eyebrow": "Top Builder AI · for ServiceTitan contractors", "title": "See the back office run on your ServiceTitan", "sub": "Read the guide, then book a 30-minute fit call", "url": "topbuilderai.com/blog"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE)
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
