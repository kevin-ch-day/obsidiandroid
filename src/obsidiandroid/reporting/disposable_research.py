"""Adapter for disposable consumer responses, reusing the retained research view."""
import copy

from obsidiandroid.governance.disposable_consumer import ConsumerDenied, MODE, fingerprint


class DisposableResearchAdapter:
    """Publish no view unless admission, complete audit and current authority pass."""
    supports_permission_queries = True

    def __init__(self, view, client):
        identities = {str(int(m['sample_id'])): m['sha256'] for m in view.samples}
        rows, receipt = client.read(identities, sorted(view.observations[0]))
        if fingerprint(rows) != fingerprint(sorted(view.observations, key=lambda r: r['obs_id'])):
            raise ConsumerDenied('VIEW_RESPONSE_SNAPSHOT_MISMATCH')
        self.view = copy.copy(view)
        self.view.observations = rows
        self.client, self.receipt = client, receipt

    def describe(self, kind='overview', value=''):
        self.client.request(action='validate', publication=self.receipt['publication'])
        result = self.view.describe(kind, value)
        self.client.request(action='validate', publication=self.receipt['publication'])
        result['evidence_mode'] = MODE
        result['publication_id'] = self.receipt['publication']
        result['permission_consumer_availability'] = dict(
            result['permission_consumer_availability'], mode=MODE)
        result['production_authorized'] = False
        return result

    def rollback(self):
        return self.client.request(action='rollback')
