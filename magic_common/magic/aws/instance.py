import logging
from datetime import datetime
from typing import Optional

import requests


DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
REBALANCE_RECOMMENDATION_URL = "http://169.254.169.254/latest/meta-data/events/recommendations/rebalance"
INSTANCE_ACTION_URL = "http://169.254.169.254/latest/meta-data/spot/instance-action"


def get_instance_rebalance_recommendations() -> Optional[datetime]:
    """
    https://docs.aws.amazon.com/zh_cn/AWSEC2/latest/UserGuide/rebalance-recommendations.html
    """
    try:
        resp = requests.get(REBALANCE_RECOMMENDATION_URL)
        if resp.status_code == 404:
            return None
        data = resp.json()
        notice_time_str = data.get('noticeTime')
        notice_time = datetime.strptime(notice_time_str, DATE_FORMAT)
        return notice_time
    except Exception:
        logging.exception(f'failed to get rebalance recommendations')
        return None


def get_instance_action() -> Optional[datetime]:
    """
    https://docs.aws.amazon.com/zh_cn/AWSEC2/latest/UserGuide/spot-instance-termination-notices.html
    """
    try:
        resp = requests.get(INSTANCE_ACTION_URL)
        if resp.status_code == 404:
            return None
        data = resp.json()
        action = data.get('action')
        action_time_str = data.get('time')
        action_time = datetime.strptime(action_time_str, DATE_FORMAT)
        return action_time
    except Exception:
        logging.exception(f'failed to get rebalance recommendations')
        return None
