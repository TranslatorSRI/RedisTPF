import redis
class RedisConnection:
    # RedisConnection is a class that holds a connection to a redis database
    # it is a context manager and can be used in a with statement
    def __init__(self,host,port,password):
        self.r = []
        self.r.append(redis.StrictRedis(host=host, port=port, db=0))  # , password=password)
        self.r.append(redis.StrictRedis(host=host, port=port, db=1))  # , password=password)
        self.r.append(redis.StrictRedis(host=host, port=port, db=2))  # , password=password)
        self.r.append(redis.StrictRedis(host=host, port=port, db=3))  # , password=password)
        self.r.append(redis.StrictRedis(host=host, port=port, db=4))  # , password=password)
        self.r.append(redis.StrictRedis(host=host, port=port, db=5))  # , password=password)
        self.r.append(redis.StrictRedis(host=host, port=port, db=6))  # , password=password)
        self.p = [ rc.pipeline() for rc in self.r ]
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        for p in self.p:
            p.execute()
        for rc in self.r:
            rc.close()
    def get_pipelines(self):
        return self.p
    def flush_pipelines(self):
        for p in self.p:
            p.execute()

    def pipeline_gets(self, pipeline_id, keys, convert_to_int=True):
        """Pipeline get queries for a given pipeline id.  Return as a dictionary, removing keys that don't
        have a value."""
        for key in keys:
            self.p[pipeline_id].get(key)
        values = self.p[pipeline_id].execute()
        if convert_to_int:
            return {k:int(v) for k,v in zip(keys, values) if v is not None}
        else:
            return {k:v for k,v in zip(keys, values) if v is not None}