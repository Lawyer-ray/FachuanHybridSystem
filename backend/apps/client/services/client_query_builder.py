"""External service client."""

from django.db.models import Q, QuerySet

from apps.client.models import Client


class ClientQueryBuilder:
    def build_queryset(
        self,
        *,
        client_type: str | None = None,
        is_our_client: bool | None = None,
        search: str | None = None,
    ) -> QuerySet[Client, Client]:
        queryset = Client.objects.prefetch_related("identity_docs").order_by("-id")

        if client_type:
            queryset = queryset.filter(client_type=client_type)

        if is_our_client is not None:
            queryset = queryset.filter(is_our_client=is_our_client)

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(phone__icontains=search) | Q(id_number__icontains=search)
            )

        return queryset
