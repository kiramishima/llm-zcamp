from typing import Any
from datetime import datetime, timezone
import dlt
from rest_api import (
    RESTAPIConfig,
    check_connection,
    rest_api_source,
    rest_api_resources,
)
from dlt.sources.helpers.rest_client.paginators import BasePaginator, JSONResponsePaginator
from dlt.sources.helpers.requests import Response, Request

from dlt.destinations.adapters import lancedb_adapter

class PostBodyPaginator(BasePaginator):
    def __init__(self):
        super().__init__()
        self.cursor = None

    def update_state(self, response: Response) -> None:
        # Assuming the API returns an empty list when no more data is available
        if not response.json():
            self._has_next_page = False
        else:
            self.cursor = response.json().get("next_cursor")
            if self.cursor is None:
                self._has_next_page = False

    def update_request(self, request: Request) -> None:
        if request.json is None:
            request.json = {}

        # Add the cursor to the request body
        request.json["start_cursor"] = self.cursor

@dlt.resource(name="employee_handbook")
def rest_api_notion_resource():
    notion_config: RESTAPIConfig = {
        "client": {
            "base_url": "https://api.notion.com/v1/",
            "auth": {
                "token": dlt.secrets["sources.rest_api.notion.api_key"]
            },
            "headers":{
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
            }
        },
        "resources": [
            {
                "name": "search",
                "endpoint": {
                    "path": "search",
                    "method": "POST",
                    "paginator": PostBodyPaginator(),
                    "json": {
                        "query": "workshop",
                        "sort": {
                            "direction": "ascending",
                            "timestamp": "last_edited_time"
                        }
                    },
                    "data_selector": "results"
                }
            },
            {
                "name": "page_content",
                "endpoint": {
                    "path": "blocks/{page_id}/children",
                    "paginator": JSONResponsePaginator(),
                    "params": {
                        "page_id": {
                            "type": "resolve",
                            "resource": "search",
                            "field": "id"
                        }
                    },
                }
            }
        ]
    }

    yield from rest_api_source(notion_config,name="employee_handbook")



def extract_page_content(response):
    block_id = response["id"]
    last_edited_time = response["last_edited_time"]
    block_type = response.get("type", "Not paragraph")
    if block_type != "paragraph":
        content = ""
    else:
        try:
            content = response["paragraph"]["rich_text"][0]["plain_text"]
        except IndexError:
            content = ""
    return {
        "block_id": block_id,
        "block_type": block_type,
        "content": content,
        "last_edited_time": last_edited_time,
        "inserted_at_time": datetime.now(timezone.utc)
    }

@dlt.resource(
    name="employee_handbook",
    write_disposition="merge",
    primary_key="block_id",
    columns={"last_edited_time":{"dedup_sort":"desc"}}
    )
def rest_api_notion_incremental(
    last_edited_time = dlt.sources.incremental("last_edited_time", initial_value="2024-06-26T08:16:00.000Z",primary_key=("block_id"))
):
    last_value = last_edited_time.last_value
    print(last_value)

    for block in rest_api_notion_resource.add_map(extract_page_content):
        if not(len(block["content"])):
            continue
        yield block

@dlt.resource(name="homework")
def rest_api_notion_homework_resource():
    notion_config: RESTAPIConfig = {
        "client": {
            "base_url": "https://api.notion.com/v1/",
            "auth": {
                "token": dlt.secrets["sources.rest_api.notion.api_key"]
            },
            "headers":{
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
            }
        },
        "resources": [
            {
                "name": "search",
                "endpoint": {
                    "path": "search",
                    "method": "POST",
                    "paginator": PostBodyPaginator(),
                    "json": {
                        "query": "homework",
                        "sort": {
                            "direction": "ascending",
                            "timestamp": "last_edited_time"
                        }
                    },
                    "data_selector": "results"
                }
            },
            {
                "name": "page_content",
                "endpoint": {
                    "path": "blocks/{page_id}/children",
                    "paginator": JSONResponsePaginator(),
                    "params": {
                        "page_id": {
                            "type": "resolve",
                            "resource": "search",
                            "field": "id"
                        }
                    },
                }
            }
        ]
    }

    yield from rest_api_source(notion_config, name="homework")

@dlt.resource(
    name="homework",
    write_disposition="merge",
    primary_key="block_id",
    columns={"last_edited_time":{"dedup_sort":"desc"}}
    )
def rest_api_notion_homework_incremental(
    last_edited_time = dlt.sources.incremental("last_edited_time", initial_value="2024-06-26T08:16:00.000Z", primary_key=("block_id"))
):
    last_value = last_edited_time.last_value
    print(last_value)

    for block in rest_api_notion_homework_resource.add_map(extract_page_content):
        if not(len(block["content"])):
            continue
        yield block

def load_notion() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="company_policies",
        destination="lancedb",
        dataset_name="notion_pages",
        # full_refresh=True
    )

    load_info = pipeline.run(
        lancedb_adapter(
            rest_api_notion_incremental,
            embed="content"
        ),
        table_name="employee_handbook",
        write_disposition="merge"
    )
    print(load_info)

def load_homework() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="company_homework",
        destination="lancedb",
        dataset_name="notion_homework",
        # full_refresh=True
    )

    load_info = pipeline.run(
        lancedb_adapter(
            rest_api_notion_homework_incremental,
            embed="content"
        ),
        table_name="homework",
        write_disposition="merge"
    )
    print(load_info)

if __name__ == "__main__":
    # load_notion()
    load_homework()
