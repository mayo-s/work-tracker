"""Adds the cache rule for the static files (deploy/cloudfront.json, TASKS.md L.22) to an existing distribution:
reads the output of `aws cloudfront get-distribution-config` and writes the DistributionConfig for
`update-distribution`, everything else unchanged. The update, unlike the creation, wants every field of a cache rule
(e.g. SmoothStreaming): those not in the template come from the distribution's default rule, as AWS returns it, except
its origin request policy.

    python3 deploy/static_cache.py <cache policy id> < distribution.json > distribution-config.json
"""

import json
import pathlib
import sys

TEMPLATE = pathlib.Path(__file__).with_name('cloudfront.json')


def with_static_cache(current: dict, policy_id: str) -> dict:
    """The distribution's config with the template's cache rules, filled in with the cache policy."""
    config = current['DistributionConfig']
    template = json.loads(TEMPLATE.read_text().replace('STATIC_POLICY', policy_id))['CacheBehaviors']
    defaults = {key: value for key, value in config['DefaultCacheBehavior'].items() if key != 'OriginRequestPolicyId'}
    rules = [defaults | rule for rule in template['Items']]
    return config | {'CacheBehaviors': {'Quantity': len(rules), 'Items': rules}}


if __name__ == '__main__':
    json.dump(with_static_cache(json.load(sys.stdin), sys.argv[1]), sys.stdout, indent=2)
