from oslo.config import cfg


traffic_steering_opts = [
    cfg.ListOpt('steering_drivers',
                default=['dummy']),
]


cfg.CONF.register_opts(traffic_steering_opts, "traffic_steering")
