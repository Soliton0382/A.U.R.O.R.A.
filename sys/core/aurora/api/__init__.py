# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-api, one module per area; sys/core/script/svc_api.py builds the app from their routers
(in this order: the order of the routes)."""
MODULES = ['oai', 'runs', 'knowledge', 'projects', 'models', 'forge', 'routine_advice', 'routines', 'activity', 'documents', 'incidents', 'social', 'agents', 'access', 'system', 'backup', 'bugreport', 'preview', 'users', 'security', 'security_ciso', 'dj', 'care', 'diet', 'autonomy', 'synapses', 'voice', 'tunnel']
