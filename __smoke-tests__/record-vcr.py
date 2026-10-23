"""Colocated smoke-test runner for target-acumatica (hotglue-smoke-test)."""

import vcr

from hotglue_smoke_test.vcr.target import VCRTargetTestRunner


class TargetAcumaticaTestRunner(VCRTargetTestRunner):
    # Version lookup reads endpoint name and version, then calls that contract.
    PRESERVE_KEYS = {"version"}
    # "Bill" is both the entity path and the Type label. Scrubbing it rewrites /Bill.
    PRESERVE_VALUES = {"Default", "Bill"}

    def module(self) -> str:
        return "target_acumatica"

    def launch(self):
        from target_acumatica.target import TargetAcumatica

        TargetAcumatica.cli()

    def vcr_use_cassette(self, filter_query_parameters):
        return vcr.use_cassette(
            self.vcr_cassette_path,
            decode_compressed_response=True,
            filter_headers=list(self.FILTER_HEADERS),
            filter_post_data_parameters=list(self.TOKEN_KEYS),
            filter_query_parameters=filter_query_parameters,
            match_on=["method", "scheme", "host", "port", "path", "query", "body"],
            before_record_response=self.before_record_response,
        )


if __name__ == "__main__":
    TargetAcumaticaTestRunner.main()
