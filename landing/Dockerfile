# Top Builder AI — Founding 50 landing page. Tiny static nginx image for Cloud Run.
FROM nginx:1.27-alpine

# The page + the founder photo.
COPY index.html /usr/share/nginx/html/index.html
COPY founder.jpg /usr/share/nginx/html/founder.jpg
COPY hero.mp4 /usr/share/nginx/html/hero.mp4

# Platform demo page + its real dashboard screenshots.
COPY demo.html /usr/share/nginx/html/demo.html
COPY assets/ /usr/share/nginx/html/assets/

# Bundle B marketing pages (mirrored from index.html/faq.html).
COPY pricing.html /usr/share/nginx/html/pricing.html
COPY about.html /usr/share/nginx/html/about.html
COPY vs-servicetitan-max.html /usr/share/nginx/html/vs-servicetitan-max.html
COPY how-it-works.html /usr/share/nginx/html/how-it-works.html

# GEO layer: FAQ page + AI-crawler surfaces (llms.txt, robots.txt, sitemap.xml).
COPY faq.html /usr/share/nginx/html/faq.html
COPY llms.txt /usr/share/nginx/html/llms.txt
COPY robots.txt /usr/share/nginx/html/robots.txt
COPY sitemap.xml /usr/share/nginx/html/sitemap.xml

# Marketplace integration instructions (Procore Marketplace "Instructions URL").
COPY procore.html /usr/share/nginx/html/procore.html

# Platform + agent pages (GEO): every new top-level page MUST be COPY'd here or the nginx SPA
# fallback silently serves the homepage at its URL (HTTP 200, wrong content — poisons crawlers).
COPY agents.html /usr/share/nginx/html/agents.html
COPY buildertrend.html /usr/share/nginx/html/buildertrend.html
COPY for-procore.html /usr/share/nginx/html/for-procore.html

# Lead-magnet pages (served at /calculator, /job-profit). MUST be COPY'd or the nginx SPA fallback
# silently serves the homepage at their URLs (HTTP 200, wrong content — poisons crawlers + DM links).
COPY calculator.html /usr/share/nginx/html/calculator.html
COPY job-profit.html /usr/share/nginx/html/job-profit.html

# Tripwire offer pages + their post-purchase intake pages (Stripe redirects to the -start pages).
COPY margin-leakage-xray.html /usr/share/nginx/html/margin-leakage-xray.html
COPY ar-collections-sprint.html /usr/share/nginx/html/ar-collections-sprint.html
COPY ceo-scorecard.html /usr/share/nginx/html/ceo-scorecard.html
COPY xray-start.html /usr/share/nginx/html/xray-start.html
COPY collections-start.html /usr/share/nginx/html/collections-start.html
COPY scorecard-start.html /usr/share/nginx/html/scorecard-start.html

# Blog (the GEO content engine): the hub + every post. NOTE: this dir MUST be copied — without it the
# nginx SPA fallback (try_files … /index.html) silently serves the homepage at /blog/* (HTTP 200, wrong
# content), which poisons crawlers. Add new posts to landing/blog/ and they ship automatically.
COPY blog/ /usr/share/nginx/html/blog/

# Trade-show landing pages (one per show, served at /shows/<slug>). Like blog/, this dir MUST be copied
# or the nginx SPA fallback (try_files … /index.html) silently serves the homepage at /shows/* (HTTP 200,
# wrong content). New show pages added to landing/shows/ ship automatically.
COPY shows/ /usr/share/nginx/html/shows/

# Trust + disclosure layer: legal pages, the WebMCP manifest, and the RFC 9116 security contact.
COPY privacy.html /usr/share/nginx/html/privacy.html
COPY terms.html /usr/share/nginx/html/terms.html
COPY security.html /usr/share/nginx/html/security.html
COPY ai-policy.html /usr/share/nginx/html/ai-policy.html
COPY webmcp.js /usr/share/nginx/html/webmcp.js
COPY downloads/ /usr/share/nginx/html/downloads/
COPY .well-known/security.txt /usr/share/nginx/html/.well-known/security.txt

# IndexNow key file (Bing/IndexNow verification — must be served at the domain root).
COPY 3ba3f0446d9ef2045ecc25702f7530da.txt /usr/share/nginx/html/3ba3f0446d9ef2045ecc25702f7530da.txt

# nginx:alpine runs envsubst on /etc/nginx/templates/*.template at startup, substituting only the
# env vars that exist (so ${PORT} from Cloud Run is filled while $uri is preserved).
COPY default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080
