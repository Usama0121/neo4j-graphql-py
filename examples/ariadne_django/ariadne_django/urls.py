"""ariadne_django URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from typing import cast
from .schema import schema
from django.urls import path
from neo4j import GraphDatabase
from django.conf import settings
from django.contrib import admin
from graphql import GraphQLSchema
from django.http import HttpRequest
from ariadne.types import GraphQLResult
from ariadne import format_error, graphql_sync
from ariadne.contrib.django.views import GraphQLView as GQLView

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j123"))


class GraphQLView(GQLView):
    def execute_query(self, request: HttpRequest, data: dict) -> GraphQLResult:
        if callable(self.context_value):
            context_value = {'driver': driver, 'request': self.context_value(request)}  # pylint: disable=not-callable
        else:
            context_value = {'driver': driver, 'request': self.context_value or request}

        return graphql_sync(
            cast(GraphQLSchema, self.schema),
            data,
            context_value=context_value,
            root_value=self.root_value,
            debug=settings.DEBUG,
            logger=self.logger,
            validation_rules=self.validation_rules,
            error_formatter=self.error_formatter or format_error,
            middleware=self.middleware,
        )


urlpatterns = [
    path('admin/', admin.site.urls),
    path('graphql/', GraphQLView.as_view(schema=schema), name='graphql'),
]
