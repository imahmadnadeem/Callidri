import redis
try:
    pool = redis.ConnectionPool(max_idle_connections=5)
    print("max_idle_connections supported")
except Exception as e:
    print(e)
