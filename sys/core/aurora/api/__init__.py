# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-api, one module per area; sys/core/script/svc_api.py builds the app from their routers
(in this order: the order of the routes)."""
MODULES = ['oai', 'runs', 'knowledge', 'uploads', 'updates', 'harvester', 'projects', 'projects_plan', 'projects_conduct', 'projects_print', 'projects_view', 'models', 'models_custom', 'accounts', 'oauth', 'places', 'forge', 'routine_advice', 'routines', 'rem', 'activity', 'usage', 'documents', 'incidents', 'social', 'agents', 'access', 'system', 'backup', 'bugreport', 'preview', 'users', 'security', 'security_ciso', 'firewalls', 'today', 'edge', 'astro', 'astro_cam', 'dj', 'care', 'diet', 'calendar', 'autonomy', 'synapses', 'voice', 'interpret', 'line', 'phone_app', 'tunnel', 'https', 'home']
