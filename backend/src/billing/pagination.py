from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Goal 6 requires the total number of matches, which `count` provides."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
