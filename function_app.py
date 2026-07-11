import azure.functions as func
import logging
import os
import uuid
import requests
from datetime import datetime, timezone
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceNotFoundError

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="visitorcounter")
def visitorcounter(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Visitor counter function triggered.')

    connection_string = os.environ["COSMOS_CONNECTION_STRING"]
    table_service = TableServiceClient.from_connection_string(connection_string)
    table_client = table_service.get_table_client(table_name="VisitorCounter")

    partition_key = "site"
    row_key = "counter"

    try:
        entity = table_client.get_entity(partition_key=partition_key, row_key=row_key)
        entity["count"] = entity["count"] + 1
    except ResourceNotFoundError:
        entity = {
            "PartitionKey": partition_key,
            "RowKey": row_key,
            "count": 1
        }

    table_client.upsert_entity(entity)

    # Log this visit (IP, location, browser) — failures here must never
    # break the actual visitor count response above.
    try:
        log_visit(req, table_service)
    except Exception as e:
        logging.warning(f"Visit logging failed (counter still succeeded): {e}")

    return func.HttpResponse(
        body=f'{{"count": {entity["count"]}}}',
        mimetype="application/json",
        status_code=200
    )


def log_visit(req: func.HttpRequest, table_service: TableServiceClient):
    ip_address = req.headers.get("X-Forwarded-For", "unknown")
    # X-Forwarded-For can contain a chain of IPs (client, proxies); the first is the real client
    ip_address = ip_address.split(",")[0].strip()

    user_agent = req.headers.get("User-Agent", "unknown")

    city, region, country = "unknown", "unknown", "unknown"
    if ip_address != "unknown":
        geo_response = requests.get(
            f"http://ip-api.com/json/{ip_address}?fields=status,city,regionName,country",
            timeout=3
        )
        if geo_response.ok:
            geo_data = geo_response.json()
            if geo_data.get("status") == "success":
                city = geo_data.get("city", "unknown")
                region = geo_data.get("regionName", "unknown")
                country = geo_data.get("country", "unknown")

    log_table = table_service.get_table_client(table_name="VisitorLog")
    log_entity = {
        "PartitionKey": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "RowKey": str(uuid.uuid4()),
        "ip_address": ip_address,
        "city": city,
        "region": region,
        "country": country,
        "user_agent": user_agent,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    log_table.upsert_entity(log_entity)