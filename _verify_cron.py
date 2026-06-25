from routes import cron
print('JOBS:', cron.JOBS, cron.JOBS.exists())
print('OUTPUT_DIR:', cron.OUTPUT_DIR, cron.OUTPUT_DIR.exists())
jobs = cron.list_cron()
print('job count:', len(jobs))
for j in jobs[:3]:
    print('  ', j)
out = cron.cron_output('6537cacf1cd6')
print('output rows:', len(out), '| file:', out[0]['created_at'] if out else None)
print('content head:', repr(out[0]['content'][:120]) if out else None)
