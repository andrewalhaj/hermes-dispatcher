from routes.memory import get_galaxy
d = get_galaxy()
print({n['tier'] for n in d['nodes']})
print('knowledge count:', sum(1 for n in d['nodes'] if n['tier'] == 'knowledge'))
