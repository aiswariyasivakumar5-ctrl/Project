# MCP Runtime Sentinel - Reproducibility Makefile
# Target Submission: Springer LNCS (AI-SEC workshop at AINA-2027)

PYTHON ?= python

.PHONY: all verify tables figures full test clean release

# Default: Verify all artifacts and regenerate all publication tables and figures
all:
	$(PYTHON) scripts/reproduce_all.py

# Verify only: check dataset manifest and artifact checksums
verify:
	$(PYTHON) scripts/reproduce_all.py --verify-only

# Regenerate tables, figures, reports only without verification
regen:
	$(PYTHON) scripts/reproduce_all.py --regenerate-only

# Run full test suite
test:
	$(PYTHON) -m unittest discover -s tests

# Full reproduction: re-runs all 20-seed models, ablations, and generates all tables
full:
	$(PYTHON) scripts/reproduce_all.py --full

# Clean temporary Python cache artifacts
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Create clean distribution release archive
release:
	$(PYTHON) scripts/make_release_archive.py
