"""Train once, offline: python -m scripts.train_model --prepared PATH --output PATH."""
import argparse
import json
from src.frozen_model import train_model

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    bundle = train_model(args.prepared,args.output)
    print(json.dumps({'model_version':bundle['model_version'], 'development_count':len(bundle['partition']['development']),
                      'held_out_count':len(bundle['partition']['held_out']), 'chosen_penalizer':bundle['training']['chosen_penalizer'],
                      'output':args.output}))

if __name__ == '__main__': main()
