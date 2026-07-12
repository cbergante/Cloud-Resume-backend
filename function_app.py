import azure.functions as func
import logging
import os
import uuid
import json
import html
import requests
from datetime import datetime, timedelta, timezone
from azure.data.tables import TableServiceClient, UpdateMode
from azure.core.exceptions import ResourceNotFoundError

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

RETENTION_DAYS = 365


# ---------------------------------------------------------------------------
# PUBLIC: visitor counter (excluded from Azure AD auth — see portal setup notes)
# ---------------------------------------------------------------------------
@app.route(route="api/visitorcounter")
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
    # break the actual visitor count response above. Returns the visit's
    # date/row-key so the front end can later report time-on-site for
    # this specific visit via /api/logduration.
    visit_date = None
    visit_id = None
    try:
        visit_date, visit_id = log_visit(req, table_service)
    except Exception as e:
        logging.warning(f"Visit logging failed (counter still succeeded): {e}")

    response_body = {"count": entity["count"]}
    if visit_id:
        response_body["visit_id"] = visit_id
        response_body["visit_date"] = visit_date

    return func.HttpResponse(
        body=json.dumps(response_body),
        mimetype="application/json",
        status_code=200
    )


def strip_port(ip_address: str) -> str:
    """
    X-Forwarded-For sometimes includes the source port (e.g. '200.225.115.56:4740').
    A bare IPv4 address has zero colons; 'ipv4:port' has exactly one. IPv6 addresses
    have multiple colons and are left untouched.
    """
    if ip_address.count(":") == 1:
        return ip_address.rsplit(":", 1)[0]
    return ip_address


def log_visit(req: func.HttpRequest, table_service: TableServiceClient):
    """
    Logs one visit. Returns (partition_key, row_key) so the caller can later
    attach a time-on-site duration to this exact entry, or (None, None) if
    logging was skipped (e.g. automated test traffic).
    """
    user_agent = req.headers.get("User-Agent", "unknown")

    # Don't log our own CI/CD smoke tests as real visitor traffic.
    if "playwright" in user_agent.lower():
        logging.info("Skipping visit log: Playwright test traffic.")
        return None, None

    ip_address = req.headers.get("X-Forwarded-For", "unknown")
    ip_address = ip_address.split(",")[0].strip()
    ip_address = strip_port(ip_address)

    city, region, country = "unknown", "unknown", "unknown"
    if ip_address != "unknown":
        try:
            geo_response = requests.get(
                f"http://ip-api.com/json/{ip_address}?fields=status,message,city,regionName,country",
                timeout=3
            )
            if geo_response.ok:
                geo_data = geo_response.json()
                if geo_data.get("status") == "success":
                    city = geo_data.get("city", "unknown")
                    region = geo_data.get("regionName", "unknown")
                    country = geo_data.get("country", "unknown")
                else:
                    logging.warning(f"Geo lookup returned non-success status for {ip_address}: {geo_data}")
            else:
                logging.warning(f"Geo lookup HTTP error for {ip_address}: {geo_response.status_code} - {geo_response.text}")
        except requests.exceptions.RequestException as e:
            logging.warning(f"Geo lookup request failed for {ip_address}: {e}")

    partition_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row_key = str(uuid.uuid4())

    log_table = table_service.get_table_client(table_name="VisitorLog")
    log_entity = {
        "PartitionKey": partition_key,
        "RowKey": row_key,
        "ip_address": ip_address,
        "city": city,
        "region": region,
        "country": country,
        "user_agent": user_agent,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    log_table.upsert_entity(log_entity)

    return partition_key, row_key


# ---------------------------------------------------------------------------
# PUBLIC: time-on-site beacon. Called via navigator.sendBeacon() when a
# visitor leaves the page, so it must stay anonymous/excluded from Azure AD
# just like visitorcounter.
# ---------------------------------------------------------------------------
@app.route(route="api/logduration", methods=["POST"])
def logduration(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(status_code=400)

    row_key = body.get("row_key")
    date = body.get("date")
    duration_seconds = body.get("duration_seconds")

    if not row_key or not date or duration_seconds is None:
        return func.HttpResponse(status_code=400)

    try:
        connection_string = os.environ["COSMOS_CONNECTION_STRING"]
        table_service = TableServiceClient.from_connection_string(connection_string)
        log_table = table_service.get_table_client(table_name="VisitorLog")

        update_entity = {
            "PartitionKey": date,
            "RowKey": row_key,
            "duration_seconds": duration_seconds
        }
        # Merge, not replace — only adds/updates this one field, leaving the
        # rest of the log entry (IP, location, etc.) exactly as it was.
        log_table.update_entity(update_entity, mode=UpdateMode.MERGE)
    except Exception as e:
        logging.warning(f"Failed to log duration for {row_key}: {e}")

    return func.HttpResponse(status_code=204)


# ---------------------------------------------------------------------------
# PRIVATE: everything below requires Azure AD sign-in (enforced at the
# platform level via Easy Auth). These functions use Anonymous auth_level
# because Easy Auth already gates access before a request reaches this code.
# ---------------------------------------------------------------------------

def get_visitor_count(table_service: TableServiceClient) -> int:
    table_client = table_service.get_table_client(table_name="VisitorCounter")
    try:
        entity = table_client.get_entity(partition_key="site", row_key="counter")
        return entity["count"]
    except ResourceNotFoundError:
        return 0


def get_recent_logs(table_service: TableServiceClient, limit: int = 200) -> list:
    log_table = table_service.get_table_client(table_name="VisitorLog")
    results = []
    for entity in log_table.list_entities():
        results.append({
            "ip_address": entity.get("ip_address", ""),
            "city": entity.get("city", ""),
            "region": entity.get("region", ""),
            "country": entity.get("country", ""),
            "user_agent": entity.get("user_agent", ""),
            "timestamp": entity.get("timestamp", ""),
            "duration_seconds": entity.get("duration_seconds")
        })
    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results[:limit]


def format_duration(seconds) -> str:
    if seconds is None or seconds == "":
        return "—"
    try:
        seconds = int(seconds)
    except (ValueError, TypeError):
        return "—"
    if seconds < 60:
        return f"{seconds}s"
    minutes, remaining = divmod(seconds, 60)
    return f"{minutes}m {remaining}s"


@app.route(route="", auth_level=func.AuthLevel.ANONYMOUS)
def dashboard(req: func.HttpRequest) -> func.HttpResponse:
    """
    Server-rendered private dashboard. Protected by Azure AD (Easy Auth) at
    the platform level — this route is NOT in the excluded-paths list, so
    Azure redirects unauthenticated visitors to Microsoft sign-in before this
    code ever runs.
    """
    connection_string = os.environ["COSMOS_CONNECTION_STRING"]
    table_service = TableServiceClient.from_connection_string(connection_string)

    count = get_visitor_count(table_service)
    logs = get_recent_logs(table_service)

    rows_html = ""
    for row in logs:
        # Every field here is visitor-supplied (esp. user_agent, fully attacker-
        # controlled) — escape before embedding in HTML to prevent stored XSS
        # against whoever views this authenticated dashboard.
        rows_html += f"""
        <tr>
          <td>{html.escape(row['timestamp'])}</td>
          <td>{html.escape(row['ip_address'])}</td>
          <td>{html.escape(row['city'])}</td>
          <td>{html.escape(row['region'])}</td>
          <td>{html.escape(row['country'])}</td>
          <td>{html.escape(format_duration(row['duration_seconds']))}</td>
          <td>{html.escape(row['user_agent'])}</td>
        </tr>"""

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex, nofollow">
  <title>Visitor Dashboard</title>
  <style>
    body {{
      background-color: #000;
      color: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 20px;
    }}
    h1 {{ font-family: "Courier New", Consolas, monospace; color: #0F0; }}
    .count-box {{
      display: inline-block;
      border: 1px solid #0F0;
      border-radius: 6px;
      padding: 14px 20px;
      margin-bottom: 20px;
      font-family: "Courier New", Consolas, monospace;
    }}
    .count-box .number {{ font-size: 2em; color: #0F0; }}
    .controls {{ margin-bottom: 16px; }}
    .controls a, .controls button {{
      font-family: "Courier New", Consolas, monospace;
      color: #0F0;
      background-color: #111;
      border: 1px solid #0F0;
      padding: 8px 12px;
      border-radius: 4px;
      text-decoration: none;
      cursor: pointer;
      margin-right: 8px;
    }}
    .controls button.danger {{ color: #f55; border-color: #f55; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
    th, td {{
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid #333;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 240px;
    }}
    th {{ color: #0F0; font-family: "Courier New", Consolas, monospace; }}
    tr:hover {{ background-color: #111; }}
  </style>
</head>
<body>
  <h1>Visitor Dashboard</h1>

  <div class="count-box">
    Total page views<br>
    <span class="number">{count}</span>
  </div>

  <div class="controls">
    <a href="?">Refresh</a>
    <form method="POST" action="/api/clearvisitorlogs" style="display:inline;"
          onsubmit="return confirm('Permanently delete ALL visitor log entries? This cannot be undone.');">
      <button type="submit" class="danger">Clear All Entries</button>
    </form>
    <a href="/.auth/logout">Sign out</a>
  </div>

  <table>
    <thead>
      <tr>
        <th>Timestamp (UTC)</th>
        <th>IP Address</th>
        <th>City</th>
        <th>Region</th>
        <th>Country</th>
        <th>Time on Site</th>
        <th>Browser / OS</th>
      </tr>
    </thead>
    <tbody>{rows_html}
    </tbody>
  </table>
</body>
</html>"""

    return func.HttpResponse(body=page, mimetype="text/html", status_code=200)


@app.route(route="api/getvisitorlogs", auth_level=func.AuthLevel.ANONYMOUS)
def getvisitorlogs(req: func.HttpRequest) -> func.HttpResponse:
    """JSON API version of the log data. Protected by Azure AD via Easy Auth."""
    connection_string = os.environ["COSMOS_CONNECTION_STRING"]
    table_service = TableServiceClient.from_connection_string(connection_string)

    try:
        limit = int(req.params.get("limit", 200))
    except ValueError:
        limit = 200

    results = get_recent_logs(table_service, limit=limit)

    return func.HttpResponse(
        body=json.dumps(results),
        mimetype="application/json",
        status_code=200
    )


@app.route(route="api/clearvisitorlogs", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def clearvisitorlogs(req: func.HttpRequest) -> func.HttpResponse:
    """Deletes every entry in VisitorLog. Protected by Azure AD via Easy Auth."""
    connection_string = os.environ["COSMOS_CONNECTION_STRING"]
    table_service = TableServiceClient.from_connection_string(connection_string)
    log_table = table_service.get_table_client(table_name="VisitorLog")

    deleted_count = 0
    for entity in log_table.list_entities():
        try:
            log_table.delete_entity(partition_key=entity["PartitionKey"], row_key=entity["RowKey"])
            deleted_count += 1
        except Exception as e:
            logging.warning(f"Failed to delete entity during clear-all: {e}")

    logging.info(f"Cleared all visitor log entries. Deleted {deleted_count}.")

    return func.HttpResponse(status_code=302, headers={"Location": "/"})


@app.timer_trigger(schedule="0 0 3 * * *", arg_name="mytimer", run_on_startup=False)
def cleanup_visitor_logs(mytimer: func.TimerRequest) -> None:
    """
    Runs daily at 03:00 UTC. Deletes VisitorLog entries older than
    RETENTION_DAYS, using the date-string PartitionKey for an efficient
    lexicographic range query.
    """
    logging.info("Visitor log cleanup function triggered.")

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")

    connection_string = os.environ["COSMOS_CONNECTION_STRING"]
    table_service = TableServiceClient.from_connection_string(connection_string)
    log_table = table_service.get_table_client(table_name="VisitorLog")

    query_filter = f"PartitionKey lt '{cutoff_date}'"
    old_entities = log_table.query_entities(query_filter=query_filter)

    deleted_count = 0
    for entity in old_entities:
        try:
            log_table.delete_entity(partition_key=entity["PartitionKey"], row_key=entity["RowKey"])
            deleted_count += 1
        except Exception as e:
            logging.warning(f"Failed to delete log entry {entity['PartitionKey']}/{entity['RowKey']}: {e}")

    logging.info(
        f"Visitor log cleanup complete. Deleted {deleted_count} entries older than {cutoff_date} "
        f"(retention: {RETENTION_DAYS} days)."
    )