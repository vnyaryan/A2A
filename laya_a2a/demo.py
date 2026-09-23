import argparse

from .core import Coordinator, Incident, RuleRouter

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", choices=["rules", "laya"], default="rules")
    parser.add_argument("--checkpoint", choices=["english", "typed-decisions"], default="english")
    args = parser.parse_args()
    if args.router == "laya":
        from .laya_router import LayaRouter
        router = LayaRouter(checkpoint=args.checkpoint)
    else:
        router = RuleRouter()
    result = Coordinator(router).run(Incident("INC001", cpu=97, error_rate=.23, database_latency=820, network_latency=34, actual_owner="database_agent"))
    for message in result.messages:
        print(message)
    print("status:", result.status)
