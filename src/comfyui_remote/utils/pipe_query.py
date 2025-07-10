""""""

import getpass
import platform
import threading
import requests

_PIPEQUERY_SERVER = "http://pipequery.zro.dneg.com/v1/graphql"

_GRAPHQL_HEADERS = {
    "Content-Type": "application/graphql",
    "Accept": "application/json",
    "Connection": "keep-alive",
    "User-Agent": "dna-pq-test/0.0.0",
    "x-client-app-name": "windows-asset_browser",
    "x-client-app-version": "0.0.0",
    "x-client-billing-code": "TESTFEAT",
    "x-client-user": getpass.getuser(),
    "x-client-site": requests.get("http://dnsite/sitedata/key/short_name").json()["short_name"],
    "x-client-host": platform.node(),

} 

def pipequery_send(queries, show=None):
    """Dispatch a query to the server.
    
    Args:
        query (str): graphql query
        monitor (object): Monitor object.
    """
    headers = _GRAPHQL_HEADERS
    if show:
        headers["x-client-billing-code"] = show

    def make_request(id, url, headers, query, results):
        request = requests.post(
            url,
            headers=headers,
            data=str.encode(query),
            timeout=None  
        )
        result = request.json()
        data = result['data']['latest_versions']
        results['data']['latest_versions'].extend(data)


    threads = []
    results = {'data': {'latest_versions': []}}
    results.setdefault
    for id, query in enumerate(queries):
        threads.append(
            threading.Thread(
                target=make_request,
                args=(
                    id,
                    _PIPEQUERY_SERVER,
                    headers,
                    query,
                    results
                )
            )
        ) 
    # Start each thread
    for thread in threads:
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    return results


def create_find_by_name_tags(show, scopes, kinds, name_tags, task=None):
    """Create a find by name tags query.

    Args:
        show (str): Target show.
        scopes (list(str)): Stempaths.
        kind (list(str)): Twigtype code.
        name_tags (iterable[str, str]): Name tag pairs.
        task (str): Target task. (Default: None)

    Returns:
        str: Query.
    """
    queries = []
    collapsed_name_tags = "".join(
        "{{name:\"{0}\",value:\"{1}\"}}".format(key, value)
        for key, value in name_tags
    )

    kind_segment = "kinds:[{0}]".format(
        ",".join("\"{0}\"".format(kind) for kind in kinds)
    )
    task_segment = "" if not task else "tasks:[\"{0}\"]".format(task)

    for scope in scopes:
        queries.append(
            "{{latest_versions("
                "mode:VERSION_NUMBER,"
                "show:\"{show}\","
                "scope_names:\"{scope}\","
                "{task_segment},"
                "{kind_segment}"
                "name_tags:{{"
                    "match:EXACT,"
                    "tags:[{collapsed_name_tags}]"
                "}}"
            "){{"
            "number{{major}},"
            "name,"
            "files{{name,path,type,ondisk_sites{{short_name}}}},"
            "scope{{name}},"
            "base_name,"
            "id,"
            "kind{{id}},"
            "status"
          "}}"
          "}}".format(
            scope=scope,
            kind_segment=kind_segment,
            task_segment=task_segment,
            collapsed_name_tags=collapsed_name_tags,
            show=show
        ))
        
    return queries
