"""'$0-install AI back office' LONG-FORM SALES video BODY (~8 min) — mirrors
/blog/zero-install-ai-back-office-servicetitan.html. Reuses the backoffice image set (no new image-gen).
Scenes restricted to confirmed shapes. CTA is the final beat; do not append after it."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py")); ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)
IMG = str(HERE / "build/img/backoffice") + "/"
CACHE = HERE / "build/zeroinstall"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/zeroinstall_body.mp4"
def P(n): return IMG + n + ".jpg"

B = [
  # --- A. The problem ---
  {"vo": "If you run ServiceTitan, you already know it runs your front office well — the calls, the schedule, the dispatch board, the invoice. That's the part it was built for, and it's genuinely good at it.",
   "scene": "split_photo", "c": {"photo": P("frontoffice"), "eyebrow": "The front office", "title": "ServiceTitan runs this well", "sub": "Calls · schedule · dispatch · invoicing"}},
  {"vo": "But there's a whole other half of your business it never automated — the money, the materials, the people, the paperwork, your receivables, and your pricebook. The unglamorous machinery that decides whether a busy month is actually a profitable one.",
   "scene": "split_photo", "c": {"photo": P("backoffice_pile"), "eyebrow": "The other half", "title": "The back office it never built", "sub": "Money · Materials · People · Paperwork · A/R · Pricebook"}},
  {"vo": "And that's exactly where the margin quietly leaks. The cash you can't see coming, the materials nobody costed, the overtime nobody caught, the invoices nobody chased — most of it still tracked in spreadsheets.",
   "scene": "split_photo", "c": {"photo": P("margin_leak"), "eyebrow": "Where margin leaks", "title": "Done by hand, after hours", "sub": "And nobody can trace the leak"}},
  {"vo": "Today that work falls on you, an office manager, and a bookkeeper — doing it late, by hand, and inconsistently. It's the part of the business that runs on the owner instead of running on its own.",
   "scene": "split_photo", "c": {"photo": P("before_stress"), "eyebrow": "Who it runs on", "title": "It runs on you", "sub": "Late nights · spreadsheets · hope"}},
  {"vo": "We built eight AI agents that run that back office for you. But there's almost always one thing standing between an owner and getting started — the upfront install fee. So we built a second door.",
   "scene": "split_photo", "c": {"photo": P("team"), "eyebrow": "The one thing in the way", "title": "The upfront fee", "sub": "A setup check is a hard yes — so we fixed it"}},

  # --- B. The offer ---
  {"vo": "So here's the offer.", "scene": "chapter", "c": {"num": "01", "title": "Two ways to start"}},
  {"vo": "There are two ways in, side by side, and you pick the one that fits how your shop likes to spend. Way one: pay the one-time install — eight thousand dollars at the founding rate — and keep your monthly flexible, month to month.",
   "scene": "cards", "c": {"title": "Pick your path", "items": [("\U0001F4B3", "Pay the install · flexible monthly"), ("\U0001F193", "$0 install · prepay the year")]}},
  {"vo": "Way two: skip the install entirely. If you'd rather not write a separate setup check, just prepay your first twelve months up front, on a firm one-year term, and the eight-thousand-dollar install drops to zero.",
   "scene": "define", "c": {"eyebrow": "The offer", "term": "$0 install when you prepay", "body": "Prepay 12 months up front → the install is $0 → your founding rate is locked for life"}},
  {"vo": "Same eight agents either way. Same done-for-you onboarding. Same board-ready-or-free guarantee. The only difference is whether you pay lump sum and stay flexible, or prepay the year and lock your founding rate for life.",
   "scene": "split_photo", "c": {"photo": P("handshake"), "eyebrow": "Identical product", "title": "Same agents. Same guarantee.", "sub": "Only the way you pay for setup changes"}},
  {"vo": "If the lump sum was the only thing standing between you and a back office that runs itself, that's the whole point of the second door. Most owner-operator shops on the fence about the fee take the prepay path.",
   "scene": "split_photo", "c": {"photo": P("hero"), "eyebrow": "Why it exists", "title": "Remove the one objection", "sub": "Turn a setup invoice into your first year"}},

  # --- C. Why we can waive it ---
  {"vo": "Now, why can we waive an eight-thousand-dollar install?", "scene": "chapter", "c": {"num": "02", "title": "Why we can waive it"}},
  {"vo": "Because the install isn't a markup or a gate — it's genuine, done-for-you work, and it's worth being specific about. First, we connect your systems: we OAuth-connect your existing ServiceTitan and QuickBooks and vault the credentials, encrypted, never stored in the clear.",
   "scene": "split_photo", "c": {"photo": P("command_center"), "eyebrow": "Step one", "title": "We connect your systems", "sub": "ServiceTitan + QuickBooks · credentials vaulted"}},
  {"vo": "Then we map your data and train the agents. We match your pricebook to your supplier files and your payroll to your rules, and we teach all eight agents your shop — your dunning cadence, your dispatch priorities, your margin targets.",
   "scene": "cards", "c": {"title": "What the install actually does", "items": [("\U0001F50C", "Connect ServiceTitan + QuickBooks"), ("\U0001F5FA️", "Map pricebook · suppliers · payroll"), ("\U0001F9E0", "Train all 8 agents on your shop")]}},
  {"vo": "That's a real services engagement, not a license key and a manual. When you prepay the year, that first year covers the onboarding — so we can drop the separate fee without doing the work for free. Same setup, paid a different way, and the risk stays ours.",
   "scene": "split_photo", "c": {"photo": P("agent_review"), "eyebrow": "Honest, not a gimmick", "title": "The prepaid year covers the setup", "sub": "Board-ready or it's free — the risk is ours"}},

  # --- D. What you get: the 8 agents ---
  {"vo": "So what are you actually getting, either way you pay? Eight self-learning agents installed on the ServiceTitan you already run. Two of them go head to head with ServiceTitan's own AI and win, and six run a back office it has no agent for.",
   "scene": "chapter", "c": {"num": "03", "title": "What you actually get"}},
  {"vo": "First, Booking. It answers, qualifies, and values every inbound call, including after-hours and overflow — so you can see what your phones are actually worth and stop leaking booked work to voicemail.",
   "scene": "photo_overlay", "c": {"photo": P("frontoffice"), "overlay": "incoming", "label": "New call — after hours", "sub": "answered, qualified, booked"}},
  {"vo": "Second, Routing and Dispatch. It assigns by drive time and margin, parts on hand, and overtime — not distance alone — and triages incoming work by priority. It won't send a truck without the right part, or quietly stack overtime onto one tech.",
   "scene": "split_photo", "c": {"photo": P("command_center"), "eyebrow": "Agent 2 · Dispatch", "title": "Routing that sees margin", "sub": "Drive time + parts + overtime + priority"}},
  {"vo": "Then the back office. Financial projects your thirty, sixty, and ninety day cash from your real jobs and books, and flags margin leakage the day it appears instead of at month-end. It reads from QuickBooks, so the cash picture matches your accounting.",
   "scene": "split_photo", "c": {"photo": P("margin_leak"), "eyebrow": "Agent 3 · Money", "title": "Financial sees your cash", "sub": "30/60/90-day cash · margin leaks, early"}},
  {"vo": "Inventory calculates reorder points, catches shrinkage, finds unbilled materials that never made it onto an invoice, and prorates partial consumables — so every ticket carries its true material cost instead of a rounded guess.",
   "scene": "split_photo", "c": {"photo": P("backoffice_pile"), "eyebrow": "Agent 4 · Materials", "title": "Inventory finds the leaks", "sub": "Unbilled materials · shrinkage · true cost"}},
  {"vo": "Workforce forecasts staffing and avoidable overtime before the week happens, reconciles payroll overtime, and surfaces the claimed-versus-clocked gaps that quietly inflate your payroll.",
   "scene": "split_photo", "c": {"photo": P("team"), "eyebrow": "Agent 5 · People", "title": "Workforce forecasts overtime", "sub": "Before the week happens, not after"}},
  {"vo": "Documents classifies, extracts, and files every form to the right ServiceTitan folder. It builds accounts payable from an emailed bill, handles warranty registration, and flags anything that needs a signature or a human's eyes.",
   "scene": "split_photo", "c": {"photo": P("agent_review"), "eyebrow": "Agent 6 · Paperwork", "title": "Documents files everything", "sub": "A/P from a bill · warranties · signatures"}},
  {"vo": "Collections works your accounts-receivable aging worklist around the clock — prioritizing invoices by age and amount, drafting the dunning emails, texts, and call scripts for your approval, and tracking promise-to-pay. It never moves money or sends on its own.",
   "scene": "split_photo", "c": {"photo": P("before_stress"), "eyebrow": "Agent 7 · A/R", "title": "Collections never sleeps", "sub": "The aging worklist, worked 24/7"}},
  {"vo": "And Pricebook keeps your material costs current as vendors raise prices, and re-prices every affected item under the sold-hour model — showing you the old price, the new price, and the margin change, for your approval.",
   "scene": "split_photo", "c": {"photo": P("hero"), "eyebrow": "Agent 8 · Pricing", "title": "Pricebook stops the drift", "sub": "Costs current · margin protected"}},

  # --- E. Why one brain ---
  {"vo": "Now, why one platform instead of ten separate apps?", "scene": "chapter", "c": {"num": "04", "title": "Why one brain beats ten apps"}},
  {"vo": "You could buy a tool for each leak — one for calls, one for reviews, one for collections texts. Stitch enough together and the stack costs more than a hire and still misses the obvious, because none of those tools see your whole shop, and none of them learn how you run it.",
   "scene": "split_photo", "c": {"photo": P("bolton_mess"), "eyebrow": "The bolt-on trap", "title": "Ten tools, ten silos", "sub": "None see the whole business"}},
  {"vo": "These agents share one brain. The dispatcher knows the parts the inventory agent is tracking, and the overtime the workforce agent is forecasting, in the same decision. And they get smarter every week from what you approve — so they sound more like your business every month, not less.",
   "scene": "split_photo", "c": {"photo": P("command_center"), "eyebrow": "One cross-agent brain", "title": "They see the whole shop", "sub": "And learn your operation weekly"}},
  {"vo": "Which is the real difference from ServiceTitan's own AI, and from bolt-on tools. Theirs are frozen the day you buy them, and siloed in one module. Ours learn, and they see the business end to end.",
   "scene": "compare", "c": {"title": "The difference", "cols": ["ServiceTitan AI", "Bolt-on tools", "Top Builder AI"],
     "rows": [("Self-learning every week", [False, False, True]), ("Sees the whole business", [False, False, True]),
              ("Tuned to your shop", [False, False, True]), ("Runs the back office", [False, True, True])]}},

  # --- F. Safe by design ---
  {"vo": "Because it's your money and your customers, it's built so it structurally cannot break anything.", "scene": "chapter", "c": {"num": "05", "title": "Safe by design"}},
  {"vo": "Advisory by default — every agent proposes, you approve. Everything is reversible with a full audit trail. And every number comes from deterministic, tested code, never from a guess. The AI explains the figure; it never invents one.",
   "scene": "secure", "c": {"title": "How it stays safe", "items": [("✅", "Advisory by default", "Every agent proposes; you approve"),
     ("↩", "Reversible", "Every action has an undo + audit trail"), ("🔒", "Deterministic", "Tested code computes every figure")]}},
  {"vo": "Access is governed too. Sensitive areas like finance and HR are walled off, and leadership grants or revokes which agents each employee can use. The brain is shared across the shop; the visibility is permissioned by role.",
   "scene": "split_photo", "c": {"photo": P("agent_review"), "eyebrow": "Governed access", "title": "Shared brain, permissioned view", "sub": "Finance & HR walled off · per-role grants"}},

  # --- G. What it's worth ---
  {"vo": "And here's why the zero-down path is a good deal for you, not a trap.", "scene": "chapter", "c": {"num": "06", "title": "What it's worth"}},
  {"vo": "The monthly is where the value lives, and one shop tends to find more than the subscription in a single place — an after-hours call that would've gone to voicemail, an aging invoice that finally gets chased, a box of flat-rate jobs that quietly leaked margin all year.",
   "scene": "split_photo", "c": {"photo": P("hero"), "eyebrow": "The honest math", "title": "It pays for the leaks it stops", "sub": "Usually bigger than the bill"}},
  {"vo": "You're not paying fifteen hundred a month for software. You're paying it to stop leaks that are usually bigger than the bill — and the install fee was only ever there to cover the setup labor, which the prepaid year already covers.",
   "scene": "split_photo", "c": {"photo": P("margin_leak"), "eyebrow": "Reframe the price", "title": "Priced against the leak", "sub": "Not against a software line item"}},

  # --- H. Transformation + close ---
  {"vo": "So here's what actually changes.", "scene": "chapter", "c": {"num": "07", "title": "What changes"}},
  {"vo": "You go from a back office you're holding together by hand and late nights, to one that runs itself in the background — and tells you the moment something needs you.",
   "scene": "before_after", "c": {"before": P("before_stress"), "after": P("after_calm"), "caption": "A back office done by hand → one that runs itself"}},
  {"vo": "Your front office stays exactly where it is, on ServiceTitan. The back office finally has agents of its own — and now you can start it with nothing down, and lock your founding rate for life.",
   "scene": "split_photo", "c": {"photo": P("handshake"), "eyebrow": "Founding 25", "title": "Keep ServiceTitan. Add the back office.", "sub": "Start with $0 down — founding rate locked"}},
  {"vo": "The founding terms are real and limited — the first twenty-five shops lock the rate, the direct line to the developer, and thirty days of free feature requests, for as long as they stay. After that, the install goes back to fifteen thousand.",
   "scene": "split_photo", "c": {"photo": P("team"), "eyebrow": "The only scarcity", "title": "First 25 founding operators", "sub": "No countdowns · no discounts to close"}},
  {"vo": "If ServiceTitan runs your front office but your back office still runs on you, that's exactly what we fix. Read the full breakdown on the blog, then book a call and pick your path — pay the install, or start at zero.",
   "scene": "cta", "c": {"eyebrow": "Top Builder AI · for ServiceTitan contractors", "title": "Start your back office with $0 down", "sub": "Read the guide, then book a 30-minute fit call", "url": "topbuilderai.com/blog"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE, voice="blend")
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
