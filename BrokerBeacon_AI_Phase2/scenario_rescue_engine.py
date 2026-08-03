"""BeaconMatch scenario rescue engine with strict, explainable parsing."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime

from flask import g, jsonify, request

OUTCOMES = {"new", "reviewed", "submitted", "approved", "denied", "withdrawn", "funded"}
DISCLAIMER = (
    "Potential paths only. Final eligibility, pricing, approval,