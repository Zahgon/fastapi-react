from rest_framework.negotiation import DefaultContentNegotiation


class JSONOnlyNegotiation(DefaultContentNegotiation):
    """Ignore `Accept`, the way FastAPI did.

    FastAPI had one representation per response and never read `Accept`; a
    request for `text/html` or `application/xml` got the JSON document anyway.
    DRF negotiates instead and answers `406 Not Acceptable` when no renderer
    matches. Every view here has exactly the renderer it answers with, so the
    first one is always the choice. Parsers are still chosen by `Content-Type`.
    """

    def select_renderer(self, request, renderers, format_suffix=None):
        renderer = renderers[0]
        return renderer, renderer.media_type
