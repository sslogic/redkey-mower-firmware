"""Export synthetic routes and coverage reports into a NEW directory."""
import argparse
import json
from pathlib import Path
from cases import CASES
from planner import build_plan

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    report={}
    for name,case in CASES.items():
        plan=build_plan(**case)
        (args.output/(name+'.json')).write_text(json.dumps(plan,indent=2)+'\n')
        report[name]=plan['metrics']
    (args.output/'coverage-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
