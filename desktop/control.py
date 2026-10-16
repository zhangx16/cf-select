import argparse,runpy,sys
import launch
parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['inspect','hourly','screen'])
args=parser.parse_args();launch.configure_environment()
sys.argv=['dns_policy.py',args.mode]+(['manual'] if args.mode=='screen' else [])
runpy.run_module('dns_policy',run_name='__main__')
