import time
from rq import Worker, Queue, Connection
from redis import Redis

redis_conn = Redis(host='redis', port=6379)

def run_agent_pipeline(proposal_dict: dict):
    print(f"Starting agent run for proposal: {proposal_dict.get('proposal_id', 'Unknown')}")
    time.sleep(3) 
    print("Agent run completed.")
    return {"status": "completed", "decision": "clear-for-submission"}

if __name__ == '__main__':
    with Connection(redis_conn):
        worker = Worker(map(Queue, ['agent_queue']))
        worker.work()