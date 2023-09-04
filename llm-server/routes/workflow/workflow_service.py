from bson import ObjectId
from utils.db import Database
from utils.vector_db.get_vector_store import get_vector_store
from utils.vector_db.store_options import StoreOptions
from routes.workflow.openapi_agent import run_openapi_agent_from_json
from utils.fetch_swagger_spec import fetch_swagger_spec
from routes.workflow.generate_openapi_payload import generate_openapi_payload
from utils.make_api_call import make_api_request
import json

db_instance = Database()
mongo = db_instance.get_db()

def run_workflow(data):
    text = data.get('text')
    swagger_url = data.get('swagger_url')
    base_prompt = data.get('base_prompt')
    headers = data.get('headers', {})
    namespace = "workflows"  # This will come from request payload later on when implementing multi-tenancy

    if not text:
        return json.dumps({"error": "text is required"}), 400

    if not base_prompt:
        return json.dumps({"error": "base_prompt is required"}), 400

    swagger_spec = fetch_swagger_spec(swagger_url)
    vector_store = get_vector_store(StoreOptions(namespace))
    documents = vector_store.similarity_search(text)

    relevant_workflow_ids = [ObjectId(doc.metadata["workflow_id"]) for doc in documents]
    relevant_records = mongo.workflows.find({"_id": {"$in": relevant_workflow_ids}})

    record = relevant_records[0]
    result = run_openapi_operations(record, swagger_spec, text)
    return result, 200, {'Content-Type': 'application/json'}

def run_openapi_operations(record, swagger_spec, text, headers):
    record_info = {"Workflow Name": record.get('name')}
    prev_api_response = ""
    for flow in record.get("flows", []):
        for step in flow.get("steps"):
            operation_id = step.get("open_api_operation_id")
            api_payload = generate_openapi_payload(swagger_spec, text)
            
            api_response = make_api_request(
                request_type = api_payload.request_type,
                url = api_payload["path"],
                body=api_payload["body"],
                params=api_payload["params"],
                query_params=api_payload["query_params"],
                headers={}
            )
            # response = run_openapi_agent_from_json(spec_json=swagger_spec, prompt=text, prev_api_response)
            # Take this operation id and the data provided in the request to call the API with the given open_api_operation_id
            # The store the response of that API to call the next API, we have to think about how this response gets stored
            record_info[operation_id] = api_response  # Store the response for this operation_id
            prev_api_response = api_response
            
    return json.dumps(record_info)
