# Self-hosted webfonts

Served from our own origin, like `static/vendor/htmx.min.js` and
`static/vendor/alpine.min.js` and for the same reason: the page must make
no third-party request before a visitor has consented to anything. A
Google Fonts `<link>` would contact a third party on first paint, which
is precisely what `templates/tracking/_tags_head.html` exists to prevent.

Both faces are licensed under the SIL Open Font License 1.1, which
permits redistribution bundled with a website.

| File | Family | Licence | Source |
| --- | --- | --- | --- |
| `inter-latin-variable.woff2` | Inter Variable (latin subset, weights 100–900) | OFL-1.1 | https://github.com/rsms/inter |
| `instrument-serif-latin-400.woff2` | Instrument Serif 400 (latin subset) | OFL-1.1 | https://github.com/Instrument/instrument-serif |

Subsets taken from the `@fontsource` builds on jsDelivr.

Inter carries UI and body text; Instrument Serif is used only at display
sizes, on the public marketing site. The signed-in workspace and the
staff dashboard keep the system font stack — see the `--font-*` tokens in
`assets/css/app.css`.

To refresh:

    curl -L -o static/fonts/inter-latin-variable.woff2 \
      https://cdn.jsdelivr.net/npm/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2
    curl -L -o static/fonts/instrument-serif-latin-400.woff2 \
      https://cdn.jsdelivr.net/npm/@fontsource/instrument-serif/files/instrument-serif-latin-400-normal.woff2
