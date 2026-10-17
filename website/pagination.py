from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size = 9
    page_size_query_param = 'page_size'
    max_page_size = 50

    def get_paginated_response(self, data):
        page = self.page
        return Response({
            'count': page.paginator.count,
            'total_pages': page.paginator.num_pages,
            'current_page': page.number,
            'next_page': page.next_page_number() if page.has_next() else None,
            'previous_page': page.previous_page_number() if page.has_previous() else None,
            'results': data,
        })
