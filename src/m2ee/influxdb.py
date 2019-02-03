#!/usr/bin/env python

import datetime
import m2ee
import m2ee.smaps as smaps
import os
import pwd
import time
from influxdb import InfluxDBClient

def write(influx_client, measurements):
    time = datetime.datetime.utcnow().replace(microsecond=0).isoformat()

    for m in measurements:
        m.update({"time":time})
        m.update({"tags":{"app":"mendix", "instance":0}})
        for field, value in m['fields'].items():
            m['fields'][field] = float(value)

    try:
        influx_client.write_points(measurements)
    except Exception, e:
        print('Failed to write to influxdb: %s' % e)


def create_influxdb_measurement(measurement, fields):
    return {
      "measurement": "mendix_runtime." + measurement,
      "fields": fields
    }


def get_requests_measurements(stats):
    requests = {}
    for sub, count in stats['requests'].items():
        requests[sub.strip('/')] = count
    return create_influxdb_measurement('requests', requests)


def get_connectionbus_measurements(stats):
    if 'connectionbus' not in stats:
        return
    connectionbus = {}
    for s in ['select', 'insert', 'update', 'delete']:
        connectionbus[s] = stats['connectionbus'][s]
    return create_influxdb_measurement('connectionbus', connectionbus)


def get_sessions_measurements(stats, graph_total_named_users):
    sessions = {}
    session_type = ['named_user_sessions', 'anonymous_sessions']
    if graph_total_named_users:
        session_type.append('named_users')
    for s in session_type:
        sessions[s] = stats['sessions'][s]
    return create_influxdb_measurement('sessions', sessions)


def get_jvmheap_measurements(stats):
    jvmheap = {}
    for k in ['tenured', 'survivor', 'eden']:
        jvmheap[k] = stats['memory'][k]
    jvmheap['free'] = (stats['memory']['max_heap'] - stats['memory']['used_heap'])
    jvmheap['limit'] = stats['memory']['max_heap']
    return create_influxdb_measurement('jvmheap', jvmheap)


def get_threadpool_measurements(stats):
    if "threadpool" not in stats:
        return

    threadpool = {}
    threadpool['min_threads'] = stats['threadpool']['min_threads']
    threadpool['max_threads'] = stats['threadpool']['max_threads']
    threadpool['threadpool_size'] = stats['threadpool']['threads']
    threadpool['active_threads'] = threadpool['threadpool_size'] - stats['threadpool']['idle_threads']
    return create_influxdb_measurement('threadpool', threadpool)


def get_cache_measurements(stats):
    if "cache" not in stats:
        return
    cache = {'total': stats['cache']['total_count']}
    return create_influxdb_measurement('cache', cache)


def get_jvm_threads_measurements(stats):
    if "threads" not in stats:
        return
    jvm_threads = {'total': stats['threads']}
    return create_influxdb_measurement('threads', jvm_threads)


def get_jvm_process_memory_measurements(stats, pid, java_version):
    if pid is None:
        return
    totals = smaps.get_smaps_rss_by_category(pid)
    if totals is None:
        return

    jpm = {}
    jpm['nativecode'] = (totals[smaps.CATEGORY_CODE] * 1024)
    jpm['jar'] = (totals[smaps.CATEGORY_JAR] * 1024)

    memory = stats['memory']

    javaheap = totals[smaps.CATEGORY_JVM_HEAP] * 1024
    for k in ['tenured', 'survivor', 'eden']:
        jpm[k] = stats['memory'][k]
    if java_version is not None and java_version >= 8:
        jpm['javaheap'] = (javaheap - memory['used_heap'] - memory['code'])
    else:
        jpm['javaheap'] = (javaheap - memory['used_heap'] - memory['code'] - memory['permanent'])

    jpm['permanent'] = stats['memory']['permanent']
    jpm['codecache'] = stats['memory']['code']
    nativemem = totals[smaps.CATEGORY_NATIVE_HEAP_ARENA] * 1024
    othermem = totals[smaps.CATEGORY_OTHER] * 1024
    if java_version is not None and java_version >= 8:
        jpm['nativemem'] = (nativemem + othermem - stats['memory']['permanent'])
        jpm['other'] = 0
    else:
        jpm['nativemem'] = nativemem
        jpm['other'] = othermem

    jpm['stacks'] = (totals[smaps.CATEGORY_THREAD_STACK] * 1024)
    jpm['total'] = (sum(totals.values()) * 1024)
    return create_influxdb_measurement('jvm_process_memory', jpm)


if __name__ == '__main__':
    m2 = m2ee.M2EE()

    #influxdb = m2.config.get_influxdb_options()
    influxdb = m2.config._conf['m2ee'].get('influxdb', {})
    influx_client = InfluxDBClient(
        host = influxdb['host'],
        port = influxdb['port'],
        username = influxdb['username'],
        database = influxdb['database'],
        password = influxdb['password'],
        ssl = True,
        verify_ssl = True,
    )

    options = m2.config.get_munin_options()

    while True:
        stats, java_version = m2ee.munin.get_stats_from_runtime(m2)

        influx = []
        influx.append(get_requests_measurements(stats))
        influx.append(get_connectionbus_measurements(stats))
        influx.append(get_sessions_measurements(stats, options.get('graph_total_named_users', True)))
        influx.append(get_jvmheap_measurements(stats))
        influx.append(get_threadpool_measurements(stats))
        influx.append(get_cache_measurements(stats))
        influx.append(get_jvm_threads_measurements(stats))
        influx.append(get_jvm_process_memory_measurements(stats, m2.runner.get_pid(), java_version))
        write(influx_client, influx)
        time.sleep(10)
