import os,runpy
os.environ['PLAYER_TOPO_PROBE']='1'
runpy.run_path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))+'/tools/author_player.py',run_name='__main__')
