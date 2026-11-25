# Search metadata and crawlers

The public entry page has Czech `lang=cs`, a descriptive title, canonical URL,
Open Graph link-preview metadata and this description:

> Diplomacie je online strategická hra pro více hráčů. Vyjednávej, uzavírej aliance a veď svůj stát k vítězství v tahové hře přímo v prohlížeči.

`public/robots.txt` allows public pages/assets and asks crawlers to avoid `/api/`,
`/admin/` and uploaded `/media/`. It points to `public/sitemap.xml`, which lists
only the public entry URL. A sitemap is a discovery hint, not an indexing guarantee.

Both Compose nginx and the school Ingress-facing nginx configuration add
`X-Robots-Tag: noindex, nofollow` to game/ranking/verification/OAuth/API/admin/media
URLs. The map uses the original request URI so internal SPA rewrites to
`index.html` cannot remove that instruction. Security headers remain inherited.
Game/ranking pages are allowed to be fetched so crawlers can read their noindex
header, while data itself remains protected by backend authentication. The
existing no-referrer meta and disabled sensitive proxy logging are preserved.

`robots.txt` controls requested crawling; it is voluntary and does not enforce
privacy. A blocked URL can still be discovered/indexed without its contents.
`noindex` asks supporting search engines not to list an accessible page. Neither
is authentication. The root meta allows indexing; the more restrictive HTTP
header excludes private routes. Search engines may use their own search-result
description instead of the supplied text.

The canonical, sitemap and Open Graph URL use the deployed public origin
`https://diplomacy.kube.sspu-opava.cz`. Update them together if the domain changes.

References:
- https://developers.google.com/search/docs/crawling-indexing/robots/intro
- https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag
- https://developers.google.com/search/docs/appearance/snippet
