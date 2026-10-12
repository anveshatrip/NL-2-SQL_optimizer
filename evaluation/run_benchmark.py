"""
run_benchmark.py
Automated evaluation script for the NL2SQL Optimizer.
Executes the benchmark query suite against the backend API,
evaluates query latency, execution cost improvement, anti-patterns caught,
and provider cost metrics, writing a summary report.
"""

import json
import time
import urllib.request
import urllib.error

BACKEND_URL = "http://localhost:8000"

def run_evaluation():
    print("=" * 70)
    print("NL2SQL OPTIMIZER - AUTOMATED BENCHMARK EVALUATION SUITE")
    print("=" * 70)

    # 1. Check health
    try:
        req = urllib.request.Request(f"{BACKEND_URL}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            print(f"[+] Connected to Backend (DB Status: {data.get('status')})")
    except Exception as e:
        print(f"[-] Backend unreachable at {BACKEND_URL}. Ensure docker-compose is running.")
        print(f"    Error: {e}")
        return

    # 2. Load Queries
    with open("benchmark_queries.json", "r", encoding="utf-8") as f:
        queries = json.load(f)

    results = []
    total_cost_reduction = 0.0
    total_antipatterns = 0
    total_llm_cost = 0.0

    print(f"\nRunning {len(queries)} benchmark queries through optimization pipeline...\n")

    for item in queries:
        qid = item["id"]
        category = item["category"]
        nl_text = item["nl_query"]

        print(f"[{qid}] ({category}): \"{nl_text}\"")

        payload = json.dumps({
            "nl_query": nl_text,
            "provider": "gemini",
            "simulate_large": True
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{BACKEND_URL}/api/optimize",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            start_t = time.time()
            with urllib.request.urlopen(req, timeout=30) as response:
                res_data = json.loads(response.read().decode())
                elapsed = time.time() - start_t

                cost_reduction = res_data.get("cost_reduction_pct", 0.0)
                ap_count = res_data.get("antipattern_count", 0)
                llm_cost = res_data.get("total_llm_cost_usd", 0.0)

                total_cost_reduction += max(cost_reduction, 0.0)
                total_antipatterns += ap_count
                total_llm_cost += llm_cost

                results.append({
                    "id": qid,
                    "category": category,
                    "query": nl_text,
                    "initial_cost": res_data.get("original_plan", {}).get("total_cost"),
                    "optimized_cost": res_data.get("optimized_plan", {}).get("total_cost"),
                    "cost_reduction_pct": cost_reduction,
                    "antipatterns_detected": ap_count,
                    "llm_cost_usd": llm_cost,
                    "status": "SUCCESS"
                })

                print(f"    ✓ Cost Reduction: {cost_reduction}% | Anti-patterns: {ap_count} | API Cost: ${llm_cost:.6f} ({elapsed:.2f}s)")

        except urllib.error.HTTPError as he:
            err_body = he.read().decode()
            print(f"    ✗ HTTP Error {he.code}: {err_body}")
            results.append({"id": qid, "status": f"FAILED ({he.code})"})
        except Exception as ex:
            print(f"    ✗ Error: {ex}")
            results.append({"id": qid, "status": f"FAILED ({ex})"})

    # 3. Output Summary
    successful = [r for r in results if r.get("status") == "SUCCESS"]
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    print(f"Total Benchmark Queries:  {len(queries)}")
    print(f"Successfully Processed:   {len(successful)} / {len(queries)}")
    if successful:
        avg_cost_red = total_cost_reduction / len(successful)
        print(f"Average Cost Reduction:   {avg_cost_red:.2f}%")
        print(f"Total Anti-Patterns Found:{total_antipatterns}")
        print(f"Total LLM Cost (USD):     ${total_llm_cost:.6f}")

    with open("benchmark_results.json", "w", encoding="utf-8") as out:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "queries_evaluated": len(queries),
            "successful": len(successful),
            "results": results
        }, out, indent=2)
    print("\nFull benchmark report saved to benchmark_results.json")

if __name__ == "__main__":
    run_evaluation()
