# Call map

Generated from the code by `sys/core/script/doc_callmap.py` (`--check` in publish.sh): who starts each script, who imports each module, who calls each API route. What each file does is in MODULE_MAP.md. A file nobody calls is listed as such: a tool run by hand, a route of an external client, or code to remove.

## Scripts: what starts them

| script | started, imported or named by |
|---|---|
| `bench_agi.py` | `script/bench_edge.py`, `script/bench_learn.py`, `script/bench_memory_days.py`, `script/bench_public.py` |
| `bench_bfcl.py` | `script/bench_public_data.py` |
| `bench_common.py` | by hand |
| `bench_compare.py` | by hand |
| `bench_domain_assign.py` | by hand |
| `bench_domains.py` | by hand |
| `bench_edge.py` | `script/bench_public.py` |
| `bench_followup.py` | by hand |
| `bench_forge.py` | `script/bench_agi.py`, `script/bench_edge.py` |
| `bench_honesty.py` | `script/bench_agi.py`, `script/bench_edge.py` |
| `bench_honeypot.py` | `script/bench_honeypot_data.py` |
| `bench_honeypot_data.py` | `script/bench_honeypot.py` |
| `bench_humaneval.py` | `script/bench_public_data.py` |
| `bench_ifeval.py` | `script/bench_public_data.py` |
| `bench_image.py` | by hand |
| `bench_learn.py` | by hand |
| `bench_memory_days.py` | `script/bench_agi.py` |
| `bench_preflight.py` | by hand |
| `bench_public.py` | `script/bench_compare.py`, `script/bench_edge.py`, `script/bench_ifeval.py`, `script/bench_learn.py`, `script/bench_public_data.py`, `script/bench_rejudge.py`, `script/bench_router.py`, `script/bench_tokens.py` |
| `bench_public_data.py` | `script/bench_bfcl.py`, `script/bench_humaneval.py`, `script/bench_ifeval.py`, `script/bench_public.py` |
| `bench_quality.py` | `script/bench_agi.py`, `script/bench_honesty.py`, `script/bench_memory_days.py`, `script/bench_public.py`, `script/bench_rejudge.py` |
| `bench_rejudge.py` | by hand |
| `bench_repair.py` | `aurora/api/agents.py`, `script/bench_agi.py` |
| `bench_retrieval.py` | `script/bench_vault_diag.py` |
| `bench_router.py` | by hand |
| `bench_synapses.py` | by hand |
| `bench_tokens.py` | by hand |
| `bench_vault_diag.py` | by hand |
| `dev_changelog.py` | `script/publish.sh` |
| `dev_license_headers.py` | by hand |
| `dev_privacy_scan.py` | `script/dev_publish.sh` |
| `dev_publish.sh` | `script/dev_privacy_scan.py`, `script/publish.sh` |
| `doc_callmap.py` | its own timer (--schedule), `script/dev_publish.sh` |
| `doc_charts.py` | `script/doc_figures.py` |
| `doc_figures.py` | by hand |
| `doc_loc.py` | `script/dev_publish.sh` |
| `doc_plugins.py` | `aurora/plg_contract.py` |
| `doc_times.py` | `script/dev_publish.sh` |
| `img_ai.py` | `aurora/mdl_image.py` |
| `img_paint.py` | `aurora/mdl_image.py` |
| `kno_import.py` | by hand |
| `kno_migrate_legacy.py` | by hand |
| `mcp_relay.py` | `aurora/prj_act.py` |
| `mem_prune.py` | by hand |
| `plg_install_all.py` | `install.sh` |
| `plg_run.py` | `aurora/plg_deps.py`, `script/doc_plugins.py`, `sys/plugins/circuits/plugin.json`, `sys/plugins/patent/plugin.json`, `sys/plugins/qr/plugin.json`, `sys/plugins/qr/server.py`, `sys/plugins/spotify/plugin.json` |
| `publish.sh` | `aurora/agt_loop.py`, `aurora/api/projects.py`, `aurora/api/routines.py`, `aurora/api/security_ciso.py`, `aurora/api/social.py`, `aurora/kno_social.py`, `aurora/kno_story_auto.py`, `aurora/prj_conduct.py`, `aurora/prj_policy.py`, `aurora/prj_talk.py`, `aurora/sec_detonate.py`, `aurora/sec_fwops.py`, `aurora/sec_fwwrite.py`, `aurora/sec_privacy.py`, `aurora/sys_approvals.py`, `aurora/sys_routines.py`, `aurora/sys_social_guard.py`, `aurora/sys_uploads.py`, `config/routine_templates.json`, `config/settings_schema.json`, `script/dev_license_headers.py`, `script/dev_privacy_scan.py`, `script/dev_publish.sh`, `script/doc_times.py`, `script/shadow_seed.py`, `script/svc_api.py`, `script/sys_install_services.py`, `sys/plugins/facebook/plugin.json`, `sys/plugins/facebook/server.py`, `sys/plugins/instagram/server.py`, `sys/plugins/mastodon/plugin.json`, `sys/plugins/projects/plugin.json`, `sys/plugins/security/plugin.json`, `sys/plugins/tiktok/server.py`, `webui/i18n/en_US.json`, `webui/js/modules/firewall.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/projects.js`, `webui/js/modules/social.js` |
| `shadow_seed.py` | its own timer (--schedule), `aurora/api/runs.py`, `aurora/kno_answer.py`, `aurora/kno_shadow.py`, `aurora/sys_ethics.py`, `script/svc_api.py`, `script/sys_domains.py` |
| `story_intro_make.py` | `aurora/kno_story.py` |
| `story_music_fetch.py` | `config/story_music.json` |
| `svc_api.py` | `aurora/agt_change.py`, `aurora/api/__init__.py`, `script/sys_install_services.py` |
| `svc_backup.py` | `aurora/sys_health.py`, `config/settings_schema.json`, `script/sys_doctor.py`, `script/sys_install_services.py`, `script/sys_users_migrate.py`, `sys/plugins/backup/plugin.json`, `sys/plugins/backup/server.py` |
| `svc_harvester.py` | `aurora/agt_change.py`, `script/sys_install_services.py` |
| `svc_llm.py` | `aurora/agt_change.py`, `script/sys_install_services.py` |
| `svc_models.py` | `aurora/agt_change.py`, `script/sys_install_services.py` |
| `svc_rem.py` | `aurora/agt_change.py`, `script/sys_install_services.py` |
| `svc_sentinel.py` | `script/sys_install_services.py` |
| `sys_backup_retime.py` | its own timer (--schedule), `script/sys_install_services.py`, `script/sys_root_sync.py` |
| `sys_calibrate.py` | `install.sh` |
| `sys_cert_perms.py` | `script/sys_install_services.py`, `script/sys_root_sync.py` |
| `sys_cloud_setup.py` | `install.sh` |
| `sys_commands_write.py` | by hand |
| `sys_doctor.py` | `install.sh` |
| `sys_domains.py` | `install.sh` |
| `sys_env_sync.py` | `aurora/sys_config.py`, `aurora/sys_formats.py`, `install.sh`, `script/dev_publish.sh`, `script/sys_doctor.py`, `script/sys_restore.py`, `script/sys_service_account.py` |
| `sys_ethics_sign.py` | `aurora/agt_forge.py`, `aurora/api/agents.py`, `aurora/mdl_modes.py`, `aurora/mdl_router.py`, `aurora/sys_cloud_consent.py`, `aurora/sys_ethics.py`, `aurora/sys_update.py`, `config/commands.json`, `install.sh`, `script/dev_license_headers.py`, `script/publish.sh`, `script/sys_doctor.py`, `script/sys_relocate.sh` |
| `sys_factory_reset.py` | `aurora/api/system.py`, `aurora/sys_reset.py`, `script/sys_install_services.py` |
| `sys_github_mcp_install.sh` | `install.sh`, `sys/plugins/github/plugin.json` |
| `sys_install_services.py` | its own timer (--schedule), `aurora/api/backup.py`, `aurora/api/security.py`, `aurora/api/system.py`, `aurora/net_https.py`, `aurora/sec_egress.py`, `install.sh`, `script/sys_relocate.sh`, `script/sys_service_account.py`, `webui/i18n/en_US.json`, `webui/i18n/it_IT.json`, `webui/js/modules/ups.js` |
| `sys_key_seal.py` | `script/sys_install_services.py` |
| `sys_model_check.py` | by hand |
| `sys_models_fetch.py` | `aurora/mdl_video.py`, `aurora/sys_capabilities.py`, `aurora/sys_features.py`, `config/models.json`, `install.sh`, `script/sys_song_install.sh`, `script/sys_tts_install.sh`, `script/sys_tts_qwen_install.sh` |
| `sys_nas_mount.py` | `aurora/sys_backup.py`, `script/sys_install_services.py`, `script/sys_root_sync.py` |
| `sys_nvidia.sh` | `install.sh` |
| `sys_profile.py` | `aurora/mdl_custom.py`, `aurora/sys_features.py`, `install.sh`, `script/sys_calibrate.py`, `script/sys_model_check.py` |
| `sys_ready.py` | `install.sh` |
| `sys_relocate.sh` | by hand |
| `sys_restore.py` | `aurora/api/backup.py`, `aurora/sys_backup_crypto.py` |
| `sys_root_sync.py` | `aurora/sys_config.py`, `script/sys_cert_perms.py`, `script/sys_ethics_sign.py`, `script/sys_install_services.py` |
| `sys_service_account.py` | `aurora/sys_config.py`, `config/commands.json`, `install.sh`, `script/sys_install_services.py` |
| `sys_song_install.sh` | `aurora/aud_song.py`, `aurora/sys_features.py`, `config/settings_schema.json`, `install.sh` |
| `sys_tts_install.sh` | `aurora/mdl_tts.py`, `aurora/sys_capabilities.py`, `aurora/sys_features.py`, `config/settings_schema.json`, `install.sh` |
| `sys_tts_qwen_install.sh` | `aurora/sys_features.py` |
| `sys_unseal_export.py` | its own timer (--schedule) |
| `sys_users_migrate.py` | `aurora/api/users.py`, `aurora/sys_users_layout.py`, `aurora/sys_users_mode.py`, `install.sh` |
| `tts_qwen_worker.py` | `aurora/mdl_tts.py` |
| `vault_realign.py` | `aurora/kno_vault_audit.py` |
| `vid_ai.py` | `aurora/mdl_video.py` |

## Library modules: who imports them

Tests are counted apart: a module imported only by tests is not used by Aurora.

| module | imported by (code) | tests |
|---|---|---|
| `aurora` | `agt_change`, `agt_forge`, `agt_forge_data`, `agt_loop`, `agt_loop_make`, `agt_react`, `api.access`, `api.accounts`, `api.activity`, `api.agents`, `api.assist`, `api.astro`, `api.autonomy`, `api.backup`, `api.bugreport`, `api.calendar`, `api.call`, `api.care`, `api.core`, `api.core_route`, `api.diet`, `api.dj`, `api.documents`, `api.edge`, `api.firewalls`, `api.forge`, `api.harvester`, `api.home`, `api.https`, `api.incidents`, `api.interpret`, `api.keys`, `api.knowledge`, `api.line`, `api.models`, `api.models_custom`, `api.oauth`, `api.people`, `api.phone_app`, `api.places`, `api.power`, `api.preview`, `api.projects`, `api.projects_conduct`, `api.projects_plan`, `api.projects_print`, `api.projects_view`, `api.radio`, `api.rem`, `api.routine_advice`, `api.routines`, `api.runs`, `api.security`, `api.security_ciso`, `api.social`, `api.synapses`, `api.system`, `api.today`, `api.tunnel`, `api.updates`, `api.uploads`, `api.usage`, `api.users`, `api.voice`, `ast_advice`, `ast_autoguide`, `ast_donut`, `ast_frames`, `ast_guidelog`, `ast_inventory`, `ast_ocal`, `ast_rotate`, `ast_sensor`, `ast_seqexport`, `ast_seqwrite`, `ast_skyplan`, `ast_skythumb`, `ast_stars`, `aud_deck`, `aud_dj`, `aud_learn`, `aud_radio`, `aud_set`, `aud_song`, `aud_song_style`, `cal_external`, `cal_share`, `cal_store`, `cal_text`, `doc_artifact`, `doc_pdf`, `doc_preview`, `fw_drivers.opnsense_read`, `fw_drivers.pfsense_read`, `hlt_diet`, `hlt_doctor`, `hlt_labs`, `hlt_store`, `hom_auto`, `hom_devices`, `hom_scenes`, `kno_acquire`, `kno_acquire_more`, `kno_anger`, `kno_answer`, `kno_attach`, `kno_deduce`, `kno_dedup`, `kno_diary`, `kno_docs`, `kno_followup`, `kno_grid`, `kno_harvest`, `kno_harvest_plan`, `kno_ingest`, `kno_lessons`, `kno_memory_seal`, `kno_mood`, `kno_mood_work`, `kno_morning`, `kno_read`, `kno_rem`, `kno_review`, `kno_self`, `kno_shadow`, `kno_social`, `kno_sources`, `kno_split`, `kno_stages`, `kno_story`, `kno_story_auto`, `kno_study`, `kno_synapse`, `kno_synapse2`, `kno_talk`, `kno_think`, `kno_trail`, `kno_train`, `kno_vault_audit`, `kno_video`, `kno_web`, `mdl_accounts`, `mdl_budget`, `mdl_cloud`, `mdl_custom`, `mdl_embedder`, `mdl_formats`, `mdl_image`, `mdl_llm`, `mdl_media`, `mdl_modes`, `mdl_remote`, `mdl_reranker`, `mdl_router`, `mdl_services`, `mdl_stt`, `mdl_tts`, `mdl_video`, `net_cfwaf`, `net_cloudflare`, `net_geo`, `net_https`, `net_trace`, `plg_access`, `plg_host`, `plg_modelnet`, `plg_sandbox`, `plg_shadow`, `plg_trash`, `prj_act`, `prj_browse`, `prj_conduct`, `prj_cover`, `prj_docs`, `prj_live`, `prj_plan`, `prj_policy`, `prj_print`, `prj_reports`, `prj_run`, `prj_sim`, `prj_talk`, `prj_term`, `prj_view`, `script/bench_common.py`, `script/bench_domain_assign.py`, `script/bench_domains.py`, `script/bench_followup.py`, `script/bench_forge.py`, `script/bench_honeypot.py`, `script/bench_image.py`, `script/bench_learn.py`, `script/bench_preflight.py`, `script/bench_public.py`, `script/bench_quality.py`, `script/bench_repair.py`, `script/bench_retrieval.py`, `script/bench_router.py`, `script/bench_synapses.py`, `script/bench_tokens.py`, `script/bench_vault_diag.py`, `script/dev_license_headers.py`, `script/dev_privacy_scan.py`, `script/img_ai.py`, `script/img_paint.py`, `script/kno_import.py`, `script/kno_migrate_legacy.py`, `script/mem_prune.py`, `script/plg_install_all.py`, `script/shadow_seed.py`, `script/story_intro_make.py`, `script/story_music_fetch.py`, `script/svc_api.py`, `script/svc_backup.py`, `script/svc_harvester.py`, `script/svc_llm.py`, `script/svc_models.py`, `script/svc_rem.py`, `script/svc_sentinel.py`, `script/sys_backup_retime.py`, `script/sys_calibrate.py`, `script/sys_cloud_setup.py`, `script/sys_commands_write.py`, `script/sys_doctor.py`, `script/sys_domains.py`, `script/sys_env_sync.py`, `script/sys_ethics_sign.py`, `script/sys_factory_reset.py`, `script/sys_install_services.py`, `script/sys_key_seal.py`, `script/sys_model_check.py`, `script/sys_nas_mount.py`, `script/sys_ready.py`, `script/sys_restore.py`, `script/sys_root_sync.py`, `script/sys_service_account.py`, `script/sys_unseal_export.py`, `script/sys_users_migrate.py`, `script/vault_realign.py`, `script/vid_ai.py`, `sec_audit`, `sec_baseline`, `sec_defence`, `sec_detonate`, `sec_egress`, `sec_egress_watch`, `sec_filecheck`, `sec_firewalls`, `sec_fwapi`, `sec_fwconf`, `sec_fwdocs`, `sec_fwmodel`, `sec_fwops`, `sec_fwplan`, `sec_fwplan_ops`, `sec_fwport`, `sec_fwpower`, `sec_fwwrite`, `sec_hostaudit`, `sec_hostfw`, `sec_hunt`, `sec_incidents`, `sec_intel`, `sec_linkcheck`, `sec_mask`, `sec_mask_spot`, `sec_netmap`, `sec_outbound`, `sec_privacy`, `sec_profile`, `sec_quiet`, `sec_report`, `sec_rules`, `sec_scorecard`, `sec_shared`, `sns_av`, `sns_clock`, `sns_weather`, `sol_index`, `sol_lexical`, `sol_reader`, `sol_search`, `sol_vault`, `sol_writer`, `sys/plugins/astro/server.py`, `sys/plugins/backup/server.py`, `sys/plugins/cad/server.py`, `sys/plugins/calendar/server.py`, `sys/plugins/circuits/server.py`, `sys/plugins/cloud/server.py`, `sys/plugins/cloudflare/server.py`, `sys/plugins/diary/server.py`, `sys/plugins/dj/server.py`, `sys/plugins/documents/my_pdfs.py`, `sys/plugins/documents/server.py`, `sys/plugins/dropbox/authorize.py`, `sys/plugins/dropbox/server.py`, `sys/plugins/expenses/server.py`, `sys/plugins/facebook/server.py`, `sys/plugins/health/server.py`, `sys/plugins/homeassistant/server.py`, `sys/plugins/instagram/server.py`, `sys/plugins/linkcheck/server.py`, `sys/plugins/logs/server.py`, `sys/plugins/nextcloud/server.py`, `sys/plugins/notes/server.py`, `sys/plugins/ntfy/server.py`, `sys/plugins/patent/server.py`, `sys/plugins/projects/server.py`, `sys/plugins/publications/server.py`, `sys/plugins/pyenv/server.py`, `sys/plugins/routines/server.py`, `sys/plugins/runs/server.py`, `sys/plugins/security/server.py`, `sys/plugins/self/server.py`, `sys/plugins/senses/server.py`, `sys/plugins/sky/server.py`, `sys/plugins/tiktok/authorize.py`, `sys/plugins/tiktok/server.py`, `sys/plugins/vista/server.py`, `sys/plugins/weather/server.py`, `sys/plugins/web/server.py`, `sys_anon`, `sys_approvals`, `sys_assist`, `sys_autonomy`, `sys_backup`, `sys_backup_crypto`, `sys_bugreport`, `sys_call`, `sys_capabilities`, `sys_cloud_consent`, `sys_commands`, `sys_config`, `sys_consoles`, `sys_devices`, `sys_disclosure`, `sys_ethics`, `sys_features`, `sys_formats`, `sys_health`, `sys_ideas`, `sys_key_recovery`, `sys_keyring`, `sys_line`, `sys_log`, `sys_logread`, `sys_metrics`, `sys_people`, `sys_persona`, `sys_phone_app`, `sys_power_hosts`, `sys_push`, `sys_reset`, `sys_routine_advice`, `sys_routine_templates`, `sys_routines`, `sys_seal`, `sys_soak`, `sys_social_guard`, `sys_tests`, `sys_trash`, `sys_update`, `sys_uploads`, `sys_ups`, `sys_usage`, `sys_user_config`, `sys_users`, `sys_users_layout`, `sys_users_mode`, `sys_users_perm` | 231 |
| `agt_calls` | `agt_loop`, `mdl_router` | 0 |
| `agt_change` | `agt_loop_make`, `api.agents` | 2 |
| `agt_forge` | `agt_forge_data`, `agt_loop`, `api.agents`, `api.forge`, `script/bench_forge.py` | 2 |
| `agt_forge_data` | `agt_forge` | 0 |
| `agt_loop` | `api.agents`, `api.routines` | 5 |
| `agt_loop_make` | `agt_loop` | 0 |
| `agt_loop_report` | `agt_loop` | 0 |
| `agt_react` | `api.agents` | 1 |
| `agt_tools` | `agt_loop` | 1 |
| `agt_vault` | `agt_loop`, `prj_act` | 1 |
| `api` | `api.users`, `script/bench_router.py`, `script/svc_api.py` | 11 |
| `api.access` | `api (MODULES)` | 0 |
| `api.accounts` | `api (MODULES)` | 0 |
| `api.activity` | `api (MODULES)`, `api.core`, `api.rem`, `api.social`, `script/svc_api.py` | 1 |
| `api.agents` | `api (MODULES)`, `api.core`, `api.core_route`, `api.projects_conduct`, `api.projects_plan`, `api.rem`, `api.routines`, `api.social`, `api.updates` | 0 |
| `api.assist` | `api (MODULES)`, `api.routines` | 1 |
| `api.astro` | `api (MODULES)`, `api.routines` | 1 |
| `api.astro_cam` | `api (MODULES)` | 1 |
| `api.autonomy` | `api (MODULES)` | 0 |
| `api.backup` | `api (MODULES)`, `api.system` | 0 |
| `api.bugreport` | `api (MODULES)` | 0 |
| `api.calendar` | `api (MODULES)`, `script/svc_api.py` | 0 |
| `api.call` | `api (MODULES)` | 0 |
| `api.care` | `api (MODULES)` | 0 |
| `api.core` | `api.access`, `api.accounts`, `api.activity`, `api.agents`, `api.assist`, `api.astro`, `api.astro_cam`, `api.autonomy`, `api.backup`, `api.bugreport`, `api.calendar`, `api.call`, `api.care`, `api.core_route`, `api.diet`, `api.dj`, `api.documents`, `api.edge`, `api.firewalls`, `api.forge`, `api.harvester`, `api.home`, `api.https`, `api.incidents`, `api.interpret`, `api.keys`, `api.knowledge`, `api.line`, `api.models`, `api.models_custom`, `api.oai`, `api.oauth`, `api.people`, `api.phone_app`, `api.places`, `api.power`, `api.preview`, `api.projects`, `api.projects_conduct`, `api.projects_plan`, `api.projects_print`, `api.projects_view`, `api.radio`, `api.rem`, `api.routine_advice`, `api.routines`, `api.runs`, `api.security`, `api.security_ciso`, `api.social`, `api.synapses`, `api.system`, `api.today`, `api.tunnel`, `api.updates`, `api.uploads`, `api.usage`, `api.users`, `api.voice`, `prj_act`, `script/bench_router.py`, `script/svc_api.py` | 4 |
| `api.core_route` | `api.agents`, `api.call`, `api.core`, `api.runs`, `script/bench_router.py` | 0 |
| `api.diet` | `api (MODULES)`, `script/svc_api.py` | 0 |
| `api.dj` | `api (MODULES)`, `api.rem` | 2 |
| `api.documents` | `api (MODULES)` | 0 |
| `api.edge` | `api (MODULES)` | 0 |
| `api.firewalls` | `api (MODULES)` | 0 |
| `api.forge` | `api (MODULES)`, `api.agents` | 0 |
| `api.harvester` | `api (MODULES)` | 0 |
| `api.home` | `api (MODULES)` | 0 |
| `api.https` | `api (MODULES)` | 0 |
| `api.incidents` | `api (MODULES)` | 0 |
| `api.interpret` | `api (MODULES)` | 0 |
| `api.keys` | `api (MODULES)` | 0 |
| `api.knowledge` | `api (MODULES)` | 1 |
| `api.line` | `api (MODULES)` | 0 |
| `api.models` | `api (MODULES)` | 0 |
| `api.models_custom` | `api (MODULES)` | 0 |
| `api.oai` | `api (MODULES)` | 0 |
| `api.oauth` | `api (MODULES)` | 0 |
| `api.people` | `api (MODULES)`, `api.routines` | 0 |
| `api.phone_app` | `api (MODULES)` | 0 |
| `api.places` | `api (MODULES)` | 0 |
| `api.power` | `api (MODULES)` | 0 |
| `api.preview` | `api (MODULES)` | 0 |
| `api.projects` | `api (MODULES)` | 0 |
| `api.projects_conduct` | `api (MODULES)` | 0 |
| `api.projects_plan` | `api (MODULES)`, `api.rem` | 0 |
| `api.projects_print` | `api (MODULES)` | 0 |
| `api.projects_view` | `api (MODULES)` | 0 |
| `api.radio` | `api (MODULES)` | 1 |
| `api.rem` | `api (MODULES)` | 0 |
| `api.routine_advice` | `api (MODULES)` | 0 |
| `api.routines` | `api (MODULES)`, `api.forge`, `api.routine_advice` | 0 |
| `api.runs` | `api (MODULES)` | 0 |
| `api.security` | `api (MODULES)`, `script/svc_api.py` | 0 |
| `api.security_ciso` | `api (MODULES)` | 0 |
| `api.social` | `api (MODULES)`, `api.routines` | 0 |
| `api.synapses` | `api (MODULES)` | 0 |
| `api.system` | `api (MODULES)`, `api.agents`, `api.incidents` | 0 |
| `api.today` | `api (MODULES)` | 0 |
| `api.tunnel` | `api (MODULES)`, `api.agents`, `api.system`, `script/svc_api.py` | 0 |
| `api.updates` | `api (MODULES)`, `api.agents`, `api.routines`, `script/svc_api.py` | 1 |
| `api.uploads` | `api (MODULES)` | 1 |
| `api.usage` | `api (MODULES)` | 0 |
| `api.users` | `api (MODULES)`, `api.activity`, `api.agents`, `api.assist`, `api.autonomy`, `api.backup`, `api.bugreport`, `api.calendar`, `api.diet`, `api.edge`, `api.firewalls`, `api.forge`, `api.harvester`, `api.https`, `api.incidents`, `api.keys`, `api.knowledge`, `api.models`, `api.models_custom`, `api.oai`, `api.people`, `api.power`, `api.rem`, `api.routines`, `api.security`, `api.security_ciso`, `api.synapses`, `api.system`, `api.updates` | 0 |
| `api.voice` | `api (MODULES)` | 0 |
| `ast_advice` | `api.astro`, `ast_donut`, `ast_ocal`, `ast_rotate`, `ast_seqwrite`, `ast_skyplan`, `sys/plugins/astro/server.py` | 2 |
| `ast_autoguide` | `api.astro`, `ast_advice` | 1 |
| `ast_camrelay` | `api.astro_cam` | 1 |
| `ast_catalog` | `api.astro`, `ast_seqwrite`, `ast_skyplan`, `ast_skythumb`, `sys/plugins/sky/server.py` | 1 |
| `ast_donut` | `api.astro`, `sys/plugins/sky/server.py` | 1 |
| `ast_frames` | `ast_sensor`, `ast_stars` | 2 |
| `ast_guidelog` | `api.astro`, `ast_advice`, `sys/plugins/astro/server.py` | 1 |
| `ast_inventory` | `api.astro`, `ast_advice`, `ast_donut`, `ast_ocal`, `ast_rotate`, `ast_sensor`, `ast_seqwrite`, `ast_skyplan`, `ast_skythumb`, `ast_stars`, `sys/plugins/astro/server.py`, `sys/plugins/sky/server.py` | 3 |
| `ast_nina` | `api.astro`, `ast_advice` | 1 |
| `ast_ocal` | `api.astro` | 1 |
| `ast_phd2` | `api.astro`, `ast_advice`, `ast_autoguide` | 1 |
| `ast_pointing` | `ast_inventory`, `sys/plugins/astro/server.py` | 1 |
| `ast_polar` | `ast_guidelog`, `sys/plugins/astro/server.py` | 1 |
| `ast_rotate` | `ast_seqwrite`, `sys/plugins/sky/server.py` | 2 |
| `ast_sensor` | `api.astro`, `ast_seqwrite`, `ast_skyplan`, `sys/plugins/astro/server.py` | 1 |
| `ast_seqexport` | `api.astro` | 1 |
| `ast_sequence` | `api.astro`, `ast_advice`, `ast_seqexport`, `ast_seqwrite` | 2 |
| `ast_seqwrite` | `api.astro`, `sys/plugins/sky/server.py` | 2 |
| `ast_sky` | `ast_skyplan` | 1 |
| `ast_skyplan` | `api.astro`, `ast_seqwrite`, `ast_skythumb`, `sys/plugins/sky/server.py` | 1 |
| `ast_skythumb` | `api.astro` | 1 |
| `ast_stars` | `api.astro`, `ast_ocal`, `sys/plugins/astro/server.py` | 1 |
| `aud_analysis` | `api.dj`, `aud_deck`, `aud_dj`, `aud_learn`, `aud_set`, `aud_song`, `aud_synth` | 5 |
| `aud_deck` | `api.dj`, `aud_dj`, `aud_set` | 2 |
| `aud_dj` | `api.dj`, `aud_deck`, `aud_song_style`, `sys/plugins/dj/server.py` | 2 |
| `aud_learn` | `api.dj`, `aud_dj`, `aud_song_style` | 1 |
| `aud_playlists` | `api.dj` | 1 |
| `aud_radio` | `api.radio`, `aud_learn` | 2 |
| `aud_set` | `api.dj` | 1 |
| `aud_song` | `api.dj` | 2 |
| `aud_song_style` | `api.dj`, `aud_song` | 3 |
| `aud_synth` | `aud_deck`, `aud_dj` | 1 |
| `cal_external` | `api.calendar`, `sys/plugins/calendar/server.py` | 1 |
| `cal_share` | `api.calendar` | 1 |
| `cal_store` | `api.calendar`, `cal_share`, `cal_text`, `sys/plugins/calendar/server.py` | 2 |
| `cal_text` | `api.calendar`, `cal_share`, `sys/plugins/calendar/server.py` | 1 |
| `doc_artifact` | `agt_loop_make`, `api.preview`, `api.projects` | 2 |
| `doc_pdf` | `api.documents`, `api.synapses`, `sys/plugins/documents/server.py`, `sys_routines`, `sys_uploads` | 2 |
| `doc_preview` | `api.preview`, `api.projects_plan`, `prj_browse` | 1 |
| `fw_drivers` | `sec_firewalls`, `sec_fwapi`, `sec_fwdocs`, `sec_fwmodel`, `sec_fwwrite`, `sec_netmap` | 4 |
| `fw_drivers.opnsense` | `fw_drivers (KINDS)`, `fw_drivers.opnsense_read` | 2 |
| `fw_drivers.opnsense_read` | `fw_drivers.opnsense` | 1 |
| `fw_drivers.opnsense_write` | `fw_drivers.opnsense` | 1 |
| `fw_drivers.pfsense` | `fw_drivers (KINDS)`, `fw_drivers.pfsense_read` | 2 |
| `fw_drivers.pfsense_read` | `fw_drivers.pfsense` | 1 |
| `fw_drivers.pfsense_write` | `fw_drivers.pfsense` | 1 |
| `fw_drivers.sophos` | `fw_drivers (KINDS)` | 2 |
| `hlt_diet` | `api.diet`, `sys/plugins/health/server.py` | 1 |
| `hlt_diet_read` | `hlt_diet` | 0 |
| `hlt_doctor` | `api.care`, `sys/plugins/health/server.py` | 1 |
| `hlt_labs` | `api.care`, `sys/plugins/health/server.py` | 1 |
| `hlt_store` | `api.care`, `api.diet`, `hlt_diet`, `hlt_labs`, `sys/plugins/health/server.py` | 3 |
| `hom_auto` | `agt_loop`, `api.home`, `api.routines` | 1 |
| `hom_devices` | `api.home`, `api.routines`, `hom_auto` | 1 |
| `hom_scenes` | `agt_loop`, `api.home`, `api.routines`, `hom_auto` | 2 |
| `img_edit` | `api.core_route` | 1 |
| `kno_about` | `kno_answer` | 1 |
| `kno_abstain` | `kno_answer`, `kno_study` | 1 |
| `kno_acquire` | `api.core_route`, `api.runs`, `kno_acquire_more`, `kno_sources`, `kno_study`, `script/svc_harvester.py`, `script/vault_realign.py` | 2 |
| `kno_acquire_more` | `kno_acquire` | 1 |
| `kno_anger` | `api.core_route`, `api.users`, `kno_answer`, `kno_mood`, `sec_mask` | 2 |
| `kno_answer` | `agt_loop`, `api.agents`, `api.call`, `api.core`, `api.core_route`, `api.forge`, `api.incidents`, `api.models_custom`, `api.routines`, `api.updates`, `kno_acquire`, `kno_followup`, `script/bench_common.py`, `script/bench_domains.py`, `script/bench_followup.py`, `script/bench_vault_diag.py` | 7 |
| `kno_arxiv` | `kno_acquire`, `kno_sources`, `script/svc_harvester.py`, `script/vault_realign.py` | 1 |
| `kno_attach` | `api.core_route`, `api.runs`, `kno_answer`, `kno_video` | 4 |
| `kno_cites` | `kno_split`, `script/bench_domains.py` | 1 |
| `kno_deduce` | `api.rem`, `api.synapses`, `kno_memory_seal` | 1 |
| `kno_dedup` | `api.knowledge`, `kno_ingest`, `kno_vault_audit`, `script/vault_realign.py` | 2 |
| `kno_diary` | `kno_memory_seal`, `kno_rem`, `sys/plugins/diary/server.py` | 1 |
| `kno_docs` | `kno_sources` | 1 |
| `kno_domain` | `kno_vault_audit`, `script/svc_harvester.py`, `script/vault_realign.py` | 1 |
| `kno_followup` | `api.core_route`, `api.runs`, `kno_answer` | 2 |
| `kno_grid` | `kno_think` | 1 |
| `kno_harvest` | `api.harvester`, `kno_harvest_plan`, `script/svc_harvester.py` | 2 |
| `kno_harvest_plan` | `script/svc_harvester.py` | 1 |
| `kno_ingest` | `api.knowledge`, `hlt_diet`, `hlt_store`, `kno_acquire`, `kno_attach`, `script/kno_import.py`, `script/svc_harvester.py` | 7 |
| `kno_interpret` | `api.interpret` | 1 |
| `kno_lessons` | `kno_answer`, `script/bench_learn.py` | 1 |
| `kno_memory_seal` | `script/svc_api.py` | 1 |
| `kno_mood` | `api.core`, `api.rem`, `kno_morning`, `kno_rem`, `mdl_tts` | 4 |
| `kno_mood_work` | `kno_mood`, `kno_self` | 1 |
| `kno_morning` | `api.rem` | 1 |
| `kno_read` | `kno_think`, `script/bench_router.py`, `script/bench_vault_diag.py` | 4 |
| `kno_rem` | `api.agents`, `api.rem`, `kno_morning`, `kno_review`, `kno_study` | 1 |
| `kno_review` | `api.rem` | 2 |
| `kno_self` | `kno_answer`, `kno_talk` | 3 |
| `kno_shadow` | `api.core_route`, `api.runs`, `kno_review`, `kno_train`, `script/shadow_seed.py`, `script/svc_api.py`, `sys_capabilities` | 4 |
| `kno_social` | `api.rem`, `api.social`, `kno_rem`, `kno_story_auto` | 1 |
| `kno_sources` | `api.harvester`, `kno_acquire_more`, `kno_docs`, `kno_harvest_plan`, `kno_shadow`, `script/svc_harvester.py`, `script/sys_calibrate.py`, `script/sys_domains.py`, `script/vault_realign.py` | 6 |
| `kno_split` | `kno_answer`, `kno_stages`, `script/bench_domains.py` | 1 |
| `kno_stages` | `kno_answer`, `kno_deduce`, `kno_interpret`, `kno_split` | 2 |
| `kno_story` | `api.social`, `kno_story_auto`, `script/story_intro_make.py`, `script/story_music_fetch.py` | 2 |
| `kno_story_auto` | `api.routines` | 1 |
| `kno_study` | `api.rem`, `kno_deduce`, `kno_morning`, `kno_review`, `kno_train` | 2 |
| `kno_synapse` | `api.knowledge`, `api.synapses`, `kno_deduce`, `kno_memory_seal`, `kno_morning`, `kno_synapse2`, `kno_trail`, `script/bench_synapses.py`, `sol_search`, `sys_capabilities` | 1 |
| `kno_synapse2` | `api.synapses` | 1 |
| `kno_talk` | `api.call` | 1 |
| `kno_think` | `api.runs`, `kno_answer` | 1 |
| `kno_trail` | `kno_answer`, `kno_stages` | 1 |
| `kno_train` | `api.rem`, `kno_deduce` | 1 |
| `kno_vault_audit` | `api.harvester`, `api.rem` | 1 |
| `kno_video` | `kno_attach` | 1 |
| `kno_web` | `kno_acquire`, `kno_read`, `sys/plugins/web/server.py` | 2 |
| `mdl_accounts` | `api.accounts`, `mdl_cloud`, `mdl_router`, `mdl_services` | 2 |
| `mdl_budget` | `api.models`, `api.users`, `mdl_cloud`, `mdl_media`, `mdl_router`, `prj_talk`, `sys_health`, `sys_usage` | 5 |
| `mdl_cloud` | `mdl_router`, `script/bench_agi.py`, `script/bench_domain_assign.py`, `script/bench_forge.py`, `script/bench_honesty.py`, `script/bench_memory_days.py`, `script/bench_public.py`, `script/bench_quality.py`, `script/bench_rejudge.py`, `script/bench_router.py` | 2 |
| `mdl_custom` | `api.models_custom`, `script/sys_model_check.py` | 1 |
| `mdl_embedder` | `script/bench_retrieval.py`, `script/svc_models.py`, `script/sys_calibrate.py` | 1 |
| `mdl_fit` | `agt_loop`, `agt_loop_report`, `mdl_router` | 2 |
| `mdl_formats` | `mdl_custom`, `mdl_llm`, `mdl_router`, `script/svc_llm.py`, `script/sys_model_check.py` | 2 |
| `mdl_gguf` | `mdl_custom`, `mdl_formats`, `script/sys_model_check.py` | 2 |
| `mdl_image` | `agt_loop_make`, `api.core_route`, `api.people`, `aud_song`, `kno_rem`, `kno_story`, `mdl_tts`, `mdl_video` | 4 |
| `mdl_llm` | `agt_loop_report`, `api.people`, `kno_answer`, `mdl_cloud`, `mdl_custom`, `mdl_router`, `script/bench_domain_assign.py`, `script/bench_forge.py`, `script/bench_learn.py`, `script/bench_public.py`, `script/bench_synapses.py`, `script/svc_harvester.py`, `script/vault_realign.py`, `sec_mask_spot`, `sys/plugins/homeassistant/server.py`, `sys/plugins/senses/server.py`, `sys/plugins/vista/server.py` | 11 |
| `mdl_media` | `api.core_route`, `api.models`, `mdl_image`, `mdl_modes`, `mdl_tts`, `mdl_video`, `sns_av`, `sys_features` | 3 |
| `mdl_modes` | `api.models`, `mdl_custom` | 2 |
| `mdl_remote` | `api.core`, `script/bench_common.py`, `script/bench_domain_assign.py`, `script/bench_domains.py`, `script/bench_followup.py`, `script/bench_learn.py`, `script/bench_retrieval.py`, `script/bench_synapses.py`, `script/bench_vault_diag.py` | 1 |
| `mdl_reranker` | `script/bench_retrieval.py`, `script/svc_models.py`, `script/sys_calibrate.py` | 2 |
| `mdl_router` | `agt_loop`, `api.accounts`, `api.care`, `api.core_route`, `api.diet`, `api.forge`, `api.models`, `api.runs`, `api.system`, `kno_answer`, `kno_grid`, `kno_read`, `kno_self`, `kno_stages`, `mdl_accounts`, `mdl_llm`, `mdl_media`, `mdl_modes`, `mdl_services`, `prj_act`, `prj_talk`, `script/bench_domain_assign.py`, `script/bench_forge.py`, `script/bench_honeypot.py`, `script/bench_learn.py`, `script/bench_preflight.py`, `script/bench_public.py`, `script/bench_router.py`, `script/svc_harvester.py`, `script/sys_cloud_setup.py`, `script/sys_doctor.py`, `script/vault_realign.py`, `sec_fwplan`, `sec_outbound`, `sys_capabilities`, `sys_features`, `sys_health`, `sys_metrics` | 17 |
| `mdl_services` | `api.accounts`, `mdl_router` | 1 |
| `mdl_stt` | `script/svc_models.py` | 1 |
| `mdl_tts` | `api.call`, `api.core`, `api.voice`, `kno_story`, `mdl_image`, `sys_capabilities` | 4 |
| `mdl_video` | `api.core_route`, `api.runs`, `script/story_intro_make.py` | 1 |
| `net_cfwaf` | `api.edge`, `api.security`, `sys/plugins/cloudflare/server.py` | 1 |
| `net_cloudflare` | `api.edge`, `api.system`, `api.tunnel`, `net_cfwaf`, `sys/plugins/cloudflare/server.py` | 2 |
| `net_geo` | `api.security`, `net_trace` | 1 |
| `net_https` | `api.agents`, `api.https`, `api.system`, `script/sys_install_services.py`, `script/sys_ready.py` | 5 |
| `net_public` | `api.agents`, `api.radio`, `aud_learn`, `aud_radio`, `cal_external`, `sys/plugins/nextcloud/server.py` | 2 |
| `net_trace` | `api.incidents`, `api.security` | 1 |
| `plg_access` | `api.agents`, `api.core` | 1 |
| `plg_away` | `plg_host` | 1 |
| `plg_contract` | `agt_forge`, `script/doc_plugins.py` | 3 |
| `plg_deps` | `api.agents`, `script/plg_install_all.py` | 1 |
| `plg_host` | `agt_forge`, `agt_loop`, `api.agents`, `api.core`, `kno_rem`, `kno_social`, `plg_access`, `script/bench_forge.py` | 9 |
| `plg_modelnet` | `plg_sandbox` | 0 |
| `plg_sandbox` | `plg_host` | 5 |
| `plg_shadow` | `agt_loop` | 2 |
| `plg_trash` | `api.agents` | 1 |
| `prj_act` | `api.projects_conduct`, `prj_talk` | 1 |
| `prj_browse` | `api.projects`, `api.projects_plan` | 1 |
| `prj_conduct` | `api.projects_conduct`, `prj_act`, `prj_live`, `prj_talk` | 4 |
| `prj_cover` | `api.projects_view` | 1 |
| `prj_cover_cad` | `prj_cover`, `prj_print` | 1 |
| `prj_docs` | `api.projects_plan` | 1 |
| `prj_live` | `api.projects_conduct` | 1 |
| `prj_plan` | `api.projects_plan` | 2 |
| `prj_policy` | `agt_loop`, `api.projects`, `kno_mood_work`, `prj_browse`, `prj_conduct`, `prj_cover`, `prj_print`, `prj_sim`, `prj_talk` | 4 |
| `prj_print` | `api.projects_print`, `prj_cover`, `prj_view` | 1 |
| `prj_print_flat` | `prj_print` | 0 |
| `prj_reports` | `agt_loop`, `api.projects` | 2 |
| `prj_run` | `agt_loop`, `api.projects_plan`, `kno_grid`, `kno_mood_work`, `prj_act`, `prj_browse`, `prj_live`, `prj_term`, `script/bench_humaneval.py`, `sys_tests` | 4 |
| `prj_sim` | `api.projects_view` | 1 |
| `prj_talk` | `api.projects_conduct`, `prj_act`, `prj_live` | 3 |
| `prj_term` | `api.projects` | 1 |
| `prj_view` | `api.projects_view`, `prj_cover` | 1 |
| `sec_audit` | `api.security_ciso`, `sys/plugins/security/server.py` | 3 |
| `sec_baseline` | `script/svc_rem.py`, `script/svc_sentinel.py` | 1 |
| `sec_defence` | `api.incidents`, `api.security`, `kno_morning`, `net_cfwaf`, `script/sys_root_sync.py`, `sec_hostfw`, `sys_autonomy` | 3 |
| `sec_detonate` | `agt_loop`, `api.knowledge`, `kno_ingest`, `kno_read`, `script/bench_honeypot.py`, `sec_linkcheck`, `sys/plugins/linkcheck/server.py` | 2 |
| `sec_egress` | `api.incidents`, `api.security`, `script/svc_sentinel.py`, `script/sys_install_services.py`, `sec_egress_watch` | 2 |
| `sec_egress_watch` | `api.incidents`, `api.security`, `script/svc_sentinel.py` | 1 |
| `sec_filecheck` | `api.knowledge`, `kno_attach` | 1 |
| `sec_firewalls` | `api.firewalls`, `api.power`, `api.security`, `api.security_ciso`, `sec_defence`, `sec_fwwrite`, `sec_netmap`, `sys_capabilities`, `sys_ups` | 3 |
| `sec_fwapi` | `api.core`, `api.incidents`, `api.security`, `api.security_ciso`, `fw_drivers.opnsense`, `fw_drivers.opnsense_read`, `fw_drivers.pfsense`, `fw_drivers.pfsense_read`, `fw_drivers.sophos`, `sec_audit`, `sec_defence`, `sec_firewalls`, `sec_fwconf`, `sec_fwops`, `sec_fwplan`, `sec_fwplan_ops`, `sec_fwport`, `sec_fwpower`, `sec_fwwrite`, `sec_hostfw`, `sec_netmap`, `sec_report`, `sys/plugins/security/server.py` | 8 |
| `sec_fwconf` | `sec_fwmodel`, `sec_fwplan`, `sec_fwport`, `sec_fwwrite`, `sys/plugins/security/server.py` | 1 |
| `sec_fwdocs` | `api.firewalls`, `api.security_ciso`, `sec_firewalls`, `sec_fwplan`, `sec_fwplan_ops`, `sys/plugins/security/server.py` | 2 |
| `sec_fwmodel` | `fw_drivers.opnsense_read`, `fw_drivers.pfsense_read`, `sec_audit`, `sec_fwops`, `sec_fwplan_ops` | 1 |
| `sec_fwops` | `sec_fwwrite` | 1 |
| `sec_fwplan` | `api.security_ciso`, `sys/plugins/security/server.py` | 3 |
| `sec_fwplan_ops` | `sec_fwplan` | 1 |
| `sec_fwport` | `api.security`, `api.security_ciso`, `sys/plugins/security/server.py` | 1 |
| `sec_fwpower` | `api.power`, `api.routines`, `sys_ups` | 2 |
| `sec_fwwrite` | `api.security_ciso`, `sec_fwplan`, `sec_fwplan_ops`, `sec_fwport`, `sys/plugins/security/server.py` | 5 |
| `sec_hostaudit` | `api.security_ciso` | 1 |
| `sec_hostfw` | `api.core`, `api.incidents`, `api.security`, `api.security_ciso`, `sec_report` | 1 |
| `sec_hunt` | `api.security_ciso`, `sys/plugins/security/server.py` | 1 |
| `sec_incidents` | `api.incidents`, `api.security`, `api.security_ciso`, `kno_mood`, `sec_report`, `sec_scorecard`, `sys_autonomy` | 7 |
| `sec_intel` | `api.incidents`, `api.security`, `net_cfwaf`, `script/svc_rem.py`, `sec_defence`, `sec_egress_watch`, `sec_fwport`, `sec_hunt`, `sec_report`, `sec_shared` | 5 |
| `sec_linkcheck` | `agt_loop`, `kno_web`, `sec_detonate`, `sec_filecheck`, `sys/plugins/linkcheck/server.py` | 2 |
| `sec_mask` | `agt_forge`, `agt_loop`, `api.accounts`, `api.social`, `kno_social`, `kno_web`, `mdl_media`, `mdl_router`, `prj_act`, `prj_talk`, `script/dev_privacy_scan.py`, `script/shadow_seed.py`, `sec_privacy`, `sys_bugreport` | 6 |
| `sec_mask_spot` | `sec_mask` | 2 |
| `sec_netmap` | `api.incidents`, `api.security`, `api.security_ciso`, `sec_fwops`, `sec_fwplan_ops`, `sec_hunt`, `sys/plugins/security/server.py`, `sys_capabilities` | 2 |
| `sec_outbound` | `api.security` | 0 |
| `sec_playbook` | `api.security_ciso`, `sys/plugins/security/server.py` | 1 |
| `sec_privacy` | `agt_loop`, `api.social`, `kno_story_auto`, `sys_bugreport` | 2 |
| `sec_profile` | `api.security`, `sec_hunt` | 1 |
| `sec_quiet` | `api.incidents` | 3 |
| `sec_report` | `api.security`, `sys/plugins/security/server.py` | 1 |
| `sec_rules` | `api.security`, `script/svc_sentinel.py`, `sec_profile` | 1 |
| `sec_scorecard` | `api.incidents` | 1 |
| `sec_sentinel` | `api.incidents`, `script/svc_sentinel.py`, `sec_hunt`, `sec_playbook`, `sec_profile`, `sys/plugins/security/server.py` | 3 |
| `sec_shared` | `api.incidents` | 1 |
| `sns_av` | `api.call`, `api.interpret`, `api.knowledge`, `kno_video`, `mdl_stt`, `sys/plugins/senses/server.py` | 2 |
| `sns_clock` | `agt_loop`, `hom_auto`, `kno_followup`, `kno_rem`, `kno_review`, `kno_self`, `kno_stages`, `kno_talk`, `script/bench_followup.py`, `script/svc_rem.py`, `sys_routines` | 2 |
| `sns_weather` | `api.places`, `api.today`, `kno_rem`, `kno_self` | 1 |
| `sol_ahead` | `sol_search` | 1 |
| `sol_index` | `kno_answer`, `kno_harvest_plan`, `kno_ingest`, `kno_memory_seal`, `script/bench_retrieval.py`, `sol_search`, `sol_writer` | 12 |
| `sol_lexical` | `kno_memory_seal`, `sol_index`, `sol_search` | 1 |
| `sol_reader` | `api.core`, `api.core_route`, `api.system`, `kno_answer`, `kno_ingest`, `kno_memory_seal`, `script/bench_quality.py`, `script/mem_prune.py`, `script/shadow_seed.py`, `sol_index`, `sol_search`, `sol_writer` | 15 |
| `sol_schema` | `api.agents`, `api.call`, `api.core_route`, `api.harvester`, `api.knowledge`, `api.runs`, `kno_acquire`, `kno_answer`, `kno_attach`, `kno_domain`, `kno_followup`, `kno_ingest`, `kno_memory_seal`, `kno_rem`, `kno_self`, `script/bench_domain_assign.py`, `script/bench_followup.py`, `script/bench_retrieval.py`, `script/kno_migrate_legacy.py`, `script/svc_harvester.py`, `sol_reader`, `sol_search`, `sol_vault`, `sol_writer` | 18 |
| `sol_search` | `kno_answer`, `kno_cites`, `kno_followup`, `kno_stages`, `script/bench_retrieval.py`, `script/bench_synapses.py` | 7 |
| `sol_vault` | `kno_harvest_plan`, `kno_memory_seal`, `kno_rem`, `kno_vault_audit`, `script/bench_domain_assign.py`, `script/bench_vault_diag.py`, `script/svc_api.py`, `script/vault_realign.py`, `sol_index`, `sol_reader`, `sol_writer` | 5 |
| `sol_writer` | `kno_answer`, `kno_ingest`, `kno_memory_seal`, `script/bench_retrieval.py` | 18 |
| `sys_anon` | `agt_loop`, `api.routines`, `api.runs` | 1 |
| `sys_approvals` | `agt_loop`, `agt_loop_make`, `api.agents`, `api.autonomy`, `api.forge`, `api.routines`, `api.security`, `api.social`, `api.updates`, `kno_story_auto`, `sys_social_guard` | 9 |
| `sys_assist` | `api.assist`, `api.core`, `api.users` | 2 |
| `sys_autonomy` | `agt_loop`, `api.autonomy`, `api.core_route`, `api.forge`, `api.incidents`, `api.updates`, `hom_devices`, `net_cfwaf`, `sec_defence`, `sec_outbound`, `sys_users_perm` | 3 |
| `sys_backup` | `api.backup`, `ast_frames`, `script/svc_backup.py`, `script/sys_doctor.py`, `script/sys_key_seal.py`, `script/sys_nas_mount.py`, `script/sys_restore.py`, `script/sys_users_migrate.py`, `sec_report`, `sys_backup_crypto`, `sys_capabilities`, `sys_health`, `sys_keyring` | 5 |
| `sys_backup_crypto` | `script/sys_key_seal.py`, `sys_backup` | 2 |
| `sys_bugreport` | `api.bugreport` | 1 |
| `sys_call` | `api.call` | 2 |
| `sys_capabilities` | `api.knowledge` | 1 |
| `sys_cloud_consent` | `mdl_modes`, `mdl_router`, `script/sys_ethics_sign.py` | 1 |
| `sys_commands` | `api.updates`, `sys_update` | 2 |
| `sys_config` | `agt_change`, `agt_forge`, `agt_forge_data`, `agt_loop`, `agt_react`, `api.autonomy`, `api.core`, `api.harvester`, `api.incidents`, `api.oauth`, `api.security`, `api.system`, `api.tunnel`, `api.updates`, `ast_inventory`, `aud_dj`, `aud_song`, `cal_external`, `cal_share`, `cal_store`, `doc_artifact`, `doc_pdf`, `doc_preview`, `hlt_diet`, `hlt_doctor`, `hlt_labs`, `hlt_store`, `hom_devices`, `kno_acquire`, `kno_anger`, `kno_answer`, `kno_attach`, `kno_deduce`, `kno_dedup`, `kno_diary`, `kno_docs`, `kno_harvest`, `kno_harvest_plan`, `kno_ingest`, `kno_lessons`, `kno_memory_seal`, `kno_mood`, `kno_mood_work`, `kno_morning`, `kno_rem`, `kno_review`, `kno_shadow`, `kno_social`, `kno_sources`, `kno_story`, `kno_story_auto`, `kno_study`, `kno_synapse`, `kno_synapse2`, `kno_talk`, `kno_trail`, `kno_train`, `kno_vault_audit`, `kno_video`, `kno_web`, `mdl_accounts`, `mdl_budget`, `mdl_cloud`, `mdl_custom`, `mdl_embedder`, `mdl_formats`, `mdl_image`, `mdl_llm`, `mdl_media`, `mdl_modes`, `mdl_remote`, `mdl_reranker`, `mdl_router`, `mdl_services`, `mdl_stt`, `mdl_tts`, `mdl_video`, `net_cfwaf`, `net_cloudflare`, `net_geo`, `net_https`, `net_trace`, `plg_access`, `plg_host`, `plg_modelnet`, `plg_sandbox`, `plg_shadow`, `plg_trash`, `prj_act`, `prj_browse`, `prj_conduct`, `prj_cover`, `prj_docs`, `prj_live`, `prj_plan`, `prj_policy`, `prj_print`, `prj_reports`, `prj_run`, `prj_sim`, `prj_talk`, `prj_term`, `prj_view`, `script/bench_common.py`, `script/bench_domain_assign.py`, `script/bench_domains.py`, `script/bench_followup.py`, `script/bench_forge.py`, `script/bench_honeypot.py`, `script/bench_image.py`, `script/bench_learn.py`, `script/bench_preflight.py`, `script/bench_quality.py`, `script/bench_repair.py`, `script/bench_retrieval.py`, `script/bench_router.py`, `script/bench_synapses.py`, `script/bench_tokens.py`, `script/bench_vault_diag.py`, `script/dev_privacy_scan.py`, `script/img_ai.py`, `script/img_paint.py`, `script/kno_import.py`, `script/kno_migrate_legacy.py`, `script/mem_prune.py`, `script/shadow_seed.py`, `script/story_intro_make.py`, `script/story_music_fetch.py`, `script/svc_api.py`, `script/svc_backup.py`, `script/svc_harvester.py`, `script/svc_llm.py`, `script/svc_models.py`, `script/svc_rem.py`, `script/svc_sentinel.py`, `script/sys_backup_retime.py`, `script/sys_calibrate.py`, `script/sys_cloud_setup.py`, `script/sys_commands_write.py`, `script/sys_doctor.py`, `script/sys_domains.py`, `script/sys_env_sync.py`, `script/sys_ethics_sign.py`, `script/sys_factory_reset.py`, `script/sys_install_services.py`, `script/sys_key_seal.py`, `script/sys_nas_mount.py`, `script/sys_ready.py`, `script/sys_restore.py`, `script/sys_root_sync.py`, `script/sys_service_account.py`, `script/sys_unseal_export.py`, `script/sys_users_migrate.py`, `script/vault_realign.py`, `script/vid_ai.py`, `sec_audit`, `sec_baseline`, `sec_defence`, `sec_detonate`, `sec_egress`, `sec_egress_watch`, `sec_filecheck`, `sec_firewalls`, `sec_fwapi`, `sec_fwconf`, `sec_fwdocs`, `sec_fwops`, `sec_fwplan`, `sec_fwplan_ops`, `sec_fwport`, `sec_fwpower`, `sec_fwwrite`, `sec_hostaudit`, `sec_hostfw`, `sec_hunt`, `sec_incidents`, `sec_intel`, `sec_linkcheck`, `sec_mask`, `sec_mask_spot`, `sec_netmap`, `sec_outbound`, `sec_privacy`, `sec_profile`, `sec_quiet`, `sec_report`, `sec_rules`, `sec_scorecard`, `sec_shared`, `sns_av`, `sns_clock`, `sns_weather`, `sol_index`, `sol_lexical`, `sol_reader`, `sol_search`, `sol_vault`, `sol_writer`, `sys/plugins/astro/server.py`, `sys/plugins/backup/server.py`, `sys/plugins/cad/server.py`, `sys/plugins/calendar/server.py`, `sys/plugins/circuits/server.py`, `sys/plugins/cloud/server.py`, `sys/plugins/cloudflare/server.py`, `sys/plugins/diary/server.py`, `sys/plugins/dj/server.py`, `sys/plugins/documents/my_pdfs.py`, `sys/plugins/documents/server.py`, `sys/plugins/dropbox/authorize.py`, `sys/plugins/dropbox/server.py`, `sys/plugins/expenses/server.py`, `sys/plugins/facebook/server.py`, `sys/plugins/health/server.py`, `sys/plugins/homeassistant/server.py`, `sys/plugins/instagram/server.py`, `sys/plugins/linkcheck/server.py`, `sys/plugins/logs/server.py`, `sys/plugins/nextcloud/server.py`, `sys/plugins/notes/server.py`, `sys/plugins/ntfy/server.py`, `sys/plugins/patent/server.py`, `sys/plugins/projects/server.py`, `sys/plugins/publications/server.py`, `sys/plugins/pyenv/server.py`, `sys/plugins/routines/server.py`, `sys/plugins/runs/server.py`, `sys/plugins/security/server.py`, `sys/plugins/self/server.py`, `sys/plugins/senses/server.py`, `sys/plugins/sky/server.py`, `sys/plugins/tiktok/authorize.py`, `sys/plugins/tiktok/server.py`, `sys/plugins/vista/server.py`, `sys/plugins/weather/server.py`, `sys_anon`, `sys_approvals`, `sys_assist`, `sys_autonomy`, `sys_backup`, `sys_backup_crypto`, `sys_bugreport`, `sys_call`, `sys_capabilities`, `sys_cloud_consent`, `sys_commands`, `sys_consoles`, `sys_devices`, `sys_disclosure`, `sys_ethics`, `sys_features`, `sys_formats`, `sys_health`, `sys_ideas`, `sys_key_recovery`, `sys_keyring`, `sys_line`, `sys_log`, `sys_logread`, `sys_people`, `sys_persona`, `sys_phone_app`, `sys_power_hosts`, `sys_push`, `sys_reset`, `sys_routine_advice`, `sys_routine_templates`, `sys_routines`, `sys_seal`, `sys_soak`, `sys_social_guard`, `sys_trash`, `sys_update`, `sys_uploads`, `sys_ups`, `sys_usage`, `sys_user_config`, `sys_users`, `sys_users_layout`, `sys_users_mode`, `sys_users_perm` | 46 |
| `sys_consoles` | `api.system` | 1 |
| `sys_context` | `agt_forge`, `agt_loop`, `api.activity`, `api.assist`, `api.astro`, `api.calendar`, `api.call`, `api.care`, `api.core`, `api.core_route`, `api.diet`, `api.dj`, `api.people`, `api.rem`, `api.routine_advice`, `api.routines`, `api.runs`, `api.tunnel`, `api.users`, `cal_external`, `hom_auto`, `hom_scenes`, `kno_attach`, `kno_self`, `mdl_budget`, `prj_act`, `sys_anon`, `sys_autonomy`, `sys_config`, `sys_log`, `sys_logread` | 9 |
| `sys_csrf` | `script/svc_api.py` | 1 |
| `sys_cycle` | `sys_backup` | 1 |
| `sys_devices` | `api.access`, `api.call`, `api.core`, `api.users`, `sys_csrf`, `sys_users_layout` | 4 |
| `sys_disclosure` | `agt_loop`, `api.calendar`, `api.core_route`, `api.social`, `doc_pdf`, `kno_social`, `kno_story`, `mdl_image`, `mdl_video`, `sys/plugins/projects/server.py` | 1 |
| `sys_ethics` | `agt_change`, `agt_forge`, `agt_loop`, `agt_loop_make`, `api.agents`, `api.autonomy`, `api.edge`, `api.models`, `kno_self`, `mdl_cloud`, `mdl_media`, `mdl_modes`, `mdl_router`, `net_cfwaf`, `plg_host`, `script/bench_preflight.py`, `script/dev_license_headers.py`, `script/svc_api.py`, `script/svc_harvester.py`, `script/svc_llm.py`, `script/svc_models.py`, `script/svc_rem.py`, `script/svc_sentinel.py`, `script/sys_ethics_sign.py`, `sec_defence`, `sys_approvals`, `sys_cloud_consent`, `sys_commands`, `sys_disclosure`, `sys_features`, `sys_health`, `sys_update` | 10 |
| `sys_features` | `agt_loop_make`, `api.bugreport`, `api.core`, `api.core_route`, `api.interpret`, `api.knowledge`, `kno_attach`, `kno_rem`, `kno_video`, `mdl_modes`, `script/sys_doctor.py`, `sys_capabilities`, `sys_health` | 5 |
| `sys_formats` | `script/sys_restore.py`, `sys_backup` | 1 |
| `sys_health` | `api.activity`, `api.bugreport`, `api.core`, `api.core_route`, `mdl_custom`, `mdl_modes`, `script/svc_harvester.py`, `script/svc_rem.py`, `script/svc_sentinel.py` | 5 |
| `sys_ideas` | `api.bugreport`, `sys_bugreport` | 3 |
| `sys_key_recovery` | `api.keys` | 1 |
| `sys_keyring` | `api.keys`, `script/svc_api.py`, `script/sys_key_seal.py`, `sys_backup_crypto`, `sys_key_recovery`, `sys_seal` | 3 |
| `sys_line` | `api.call`, `api.core`, `api.line`, `api.phone_app`, `api.routines`, `sys_call` | 2 |
| `sys_log` | `agt_change`, `agt_forge`, `agt_loop`, `api.access`, `api.activity`, `api.autonomy`, `api.core`, `api.security`, `api.system`, `api.users`, `aud_song`, `doc_pdf`, `kno_acquire`, `kno_answer`, `kno_attach`, `kno_harvest_plan`, `kno_ingest`, `kno_lessons`, `kno_memory_seal`, `kno_read`, `kno_rem`, `kno_social`, `kno_story`, `kno_story_auto`, `kno_vault_audit`, `kno_video`, `mdl_budget`, `mdl_cloud`, `mdl_embedder`, `mdl_image`, `mdl_llm`, `mdl_media`, `mdl_reranker`, `mdl_router`, `mdl_stt`, `mdl_tts`, `mdl_video`, `net_cfwaf`, `net_https`, `plg_host`, `plg_trash`, `prj_act`, `script/bench_retrieval.py`, `script/bench_synapses.py`, `script/kno_migrate_legacy.py`, `script/svc_backup.py`, `script/svc_harvester.py`, `script/svc_llm.py`, `script/svc_models.py`, `script/svc_rem.py`, `script/svc_sentinel.py`, `script/sys_cloud_setup.py`, `sec_defence`, `sec_detonate`, `sec_filecheck`, `sec_firewalls`, `sec_fwdocs`, `sec_fwport`, `sec_fwpower`, `sec_fwwrite`, `sec_incidents`, `sec_linkcheck`, `sec_mask_spot`, `sns_av`, `sns_weather`, `sol_index`, `sol_lexical`, `sol_search`, `sol_writer`, `sys_approvals`, `sys_autonomy`, `sys_backup`, `sys_logread`, `sys_power_hosts`, `sys_push`, `sys_update`, `sys_ups` | 11 |
| `sys_logread` | `agt_react`, `api.activity`, `api.agents`, `kno_mood`, `kno_rem`, `kno_self`, `sys/plugins/self/server.py`, `sys_bugreport` | 2 |
| `sys_metrics` | `api.routines`, `sys_health` | 1 |
| `sys_people` | `agt_loop`, `api.people`, `kno_self` | 1 |
| `sys_persona` | `api.users`, `kno_morning`, `kno_rem`, `kno_self`, `kno_social`, `kno_talk` | 1 |
| `sys_phone_app` | `api.phone_app` | 1 |
| `sys_power_hosts` | `api.power`, `sys_ups` | 2 |
| `sys_push` | `api.core`, `api.routines`, `script/bench_synapses.py`, `sec_outbound`, `sys_capabilities`, `sys_line`, `sys_ups` | 6 |
| `sys_replay` | `script/svc_api.py` | 1 |
| `sys_reset` | `api.system`, `script/sys_factory_reset.py` | 1 |
| `sys_routine_advice` | `api.home`, `api.routine_advice`, `hom_devices` | 2 |
| `sys_routine_templates` | `api.routine_advice` | 2 |
| `sys_routines` | `api.forge`, `api.home`, `api.knowledge`, `api.routine_advice`, `api.routines`, `api.today`, `hom_auto`, `hom_devices`, `hom_scenes`, `sys_routine_advice`, `sys_routine_templates` | 8 |
| `sys_runs` | `api.core` | 1 |
| `sys_seal` | `api.care`, `api.diet`, `api.uploads`, `cal_store`, `hlt_diet`, `hlt_doctor`, `hlt_labs`, `hlt_store`, `kno_anger`, `kno_diary`, `kno_mood`, `kno_review`, `kno_shadow`, `kno_study`, `mdl_tts`, `plg_host`, `plg_shadow`, `prj_act`, `prj_conduct`, `prj_plan`, `prj_reports`, `prj_talk`, `script/bench_forge.py`, `script/sys_unseal_export.py`, `sec_firewalls`, `sec_mask_spot`, `sec_netmap`, `sol_index`, `sol_vault`, `sys/plugins/expenses/server.py`, `sys/plugins/routines/server.py`, `sys/plugins/runs/server.py`, `sys_anon`, `sys_approvals`, `sys_assist`, `sys_ideas`, `sys_line`, `sys_log`, `sys_people`, `sys_push`, `sys_routines`, `sys_uploads` | 8 |
| `sys_soak` | `api.activity`, `script/svc_rem.py` | 1 |
| `sys_social_guard` | `agt_loop`, `api.social`, `kno_story_auto` | 1 |
| `sys_tests` | `agt_change`, `agt_loop_make`, `script/bench_repair.py`, `sys/plugins/self/server.py`, `sys_update` | 1 |
| `sys_trash` | `api.dj`, `api.documents`, `api.uploads`, `sys_uploads` | 1 |
| `sys_update` | `api.agents`, `api.routines`, `api.updates`, `sys_commands` | 2 |
| `sys_uploads` | `agt_loop_make`, `api.agents`, `api.core_route`, `api.knowledge`, `api.runs`, `api.social`, `api.uploads`, `doc_artifact`, `doc_preview`, `kno_review`, `kno_study`, `sys_routines` | 6 |
| `sys_ups` | `api.power`, `api.system`, `script/svc_rem.py` | 1 |
| `sys_usage` | `api.usage`, `sys_log`, `sys_users_layout` | 1 |
| `sys_user_config` | `api.assist`, `api.autonomy`, `api.core`, `api.oauth`, `api.system`, `api.users`, `cal_share`, `script/mem_prune.py`, `script/svc_api.py`, `script/sys_nas_mount.py`, `sec_privacy`, `sys_config`, `sys_users_layout` | 7 |
| `sys_users` | `agt_loop`, `api.autonomy`, `api.core`, `api.users`, `cal_external`, `kno_self`, `mdl_accounts`, `script/mem_prune.py`, `script/sys_users_migrate.py`, `sec_mask`, `sec_privacy`, `sys_users_layout`, `sys_users_mode` | 10 |
| `sys_users_layout` | `agt_forge`, `agt_forge_data`, `agt_react`, `api.autonomy`, `api.oauth`, `api.system`, `api.users`, `cal_store`, `kno_anger`, `kno_diary`, `kno_memory_seal`, `kno_mood`, `kno_review`, `kno_shadow`, `kno_story`, `kno_study`, `mdl_tts`, `plg_sandbox`, `plg_shadow`, `prj_conduct`, `prj_cover`, `prj_docs`, `prj_plan`, `prj_policy`, `prj_reports`, `prj_talk`, `script/bench_forge.py`, `script/svc_api.py`, `script/sys_nas_mount.py`, `script/sys_unseal_export.py`, `script/sys_users_migrate.py`, `sec_mask_spot`, `sec_privacy`, `sol_index`, `sol_vault`, `sys/plugins/runs/server.py`, `sys_anon`, `sys_approvals`, `sys_assist`, `sys_config`, `sys_consoles`, `sys_ideas`, `sys_line`, `sys_log`, `sys_push`, `sys_routines`, `sys_seal`, `sys_trash`, `sys_user_config`, `sys_users_mode` | 12 |
| `sys_users_mode` | `api.system` | 1 |
| `sys_users_perm` | `api.system`, `api.users`, `mdl_budget` | 2 |
| `txt_compress` | `kno_read`, `kno_stages`, `prj_act` | 1 |
| `txt_headlines` | `api.today` | 1 |
| `txt_ical` | `cal_external`, `cal_store`, `cal_text`, `sys/plugins/calendar/server.py` | 1 |
| `txt_lang` | `agt_loop`, `api.documents`, `api.social`, `kno_acquire`, `kno_answer`, `kno_attach`, `kno_grid`, `kno_ingest`, `kno_read`, `kno_rem`, `kno_self`, `kno_social`, `kno_stages`, `kno_story_auto`, `kno_talk`, `mdl_router`, `script/bench_quality.py`, `script/kno_migrate_legacy.py`, `script/mem_prune.py`, `sys/plugins/documents/server.py` | 1 |

## WebUI modules: who imports them

| module | imported by |
|---|---|
| `js/api.js` | `js/artifact.js`, `js/backup.js`, `js/calendar_alerts.js`, `js/cards.js`, `js/dates.js`, `js/diet.js`, `js/main.js`, `js/modules/accounts.js`, `js/modules/accounts_services.js`, `js/modules/alerts.js`, `js/modules/approvals.js`, `js/modules/astro.js`, `js/modules/astro_advice.js`, `js/modules/astro_collim.js`, `js/modules/astro_collim_live.js`, `js/modules/astro_collim_pc.js`, `js/modules/astro_imaging.js`, `js/modules/astro_live.js`, `js/modules/astro_mount.js`, `js/modules/astro_nights.js`, `js/modules/astro_sky.js`, `js/modules/astro_tuner.js`, `js/modules/aurorafw.js`, `js/modules/autonomy.js`, `js/modules/autonomy_box.js`, `js/modules/brain.js`, `js/modules/bugreport.js`, `js/modules/calendar.js`, `js/modules/calendar_form.js`, `js/modules/care.js`, `js/modules/care_diet.js`, `js/modules/care_doctor.js`, `js/modules/care_values.js`, `js/modules/chat.js`, `js/modules/chat_anon.js`, `js/modules/chat_media.js`, `js/modules/ciso.js`, `js/modules/consoles.js`, `js/modules/deductions_box.js`, `js/modules/diary.js`, `js/modules/dj.js`, `js/modules/dj_player.js`, `js/modules/dj_radio.js`, `js/modules/dj_set.js`, `js/modules/dj_styles.js`, `js/modules/dreams.js`, `js/modules/expenses.js`, `js/modules/firewall.js`, `js/modules/harvest_plan.js`, `js/modules/harvester.js`, `js/modules/home.js`, `js/modules/home_auto.js`, `js/modules/home_scenes.js`, `js/modules/hosts.js`, `js/modules/https.js`, `js/modules/ideas.js`, `js/modules/import.js`, `js/modules/interpret.js`, `js/modules/keys.js`, `js/modules/mask_view.js`, `js/modules/memory.js`, `js/modules/metrics.js`, `js/modules/models.js`, `js/modules/models_choice.js`, `js/modules/models_custom.js`, `js/modules/models_mode.js`, `js/modules/notifications.js`, `js/modules/people.js`, `js/modules/phone_app.js`, `js/modules/plugin_slot.js`, `js/modules/plugins.js`, `js/modules/project_conduct.js`, `js/modules/project_docs.js`, `js/modules/project_files.js`, `js/modules/project_page.js`, `js/modules/project_plan.js`, `js/modules/project_policy.js`, `js/modules/project_print.js`, `js/modules/project_render.js`, `js/modules/project_sim.js`, `js/modules/project_talk.js`, `js/modules/project_term.js`, `js/modules/projects.js`, `js/modules/reports.js`, `js/modules/routines.js`, `js/modules/routines_templates.js`, `js/modules/runs.js`, `js/modules/security.js`, `js/modules/security_defence.js`, `js/modules/security_edge.js`, `js/modules/security_egress_page.js`, `js/modules/security_firewalls.js`, `js/modules/security_map.js`, `js/modules/security_quiet.js`, `js/modules/security_watch.js`, `js/modules/settings.js`, `js/modules/settings_form.js`, `js/modules/social.js`, `js/modules/social_video.js`, `js/modules/status.js`, `js/modules/synapses.js`, `js/modules/today.js`, `js/modules/today_pages.js`, `js/modules/trace.js`, `js/modules/updates.js`, `js/modules/uploads.js`, `js/modules/ups.js`, `js/modules/usage.js`, `js/modules/users.js`, `js/modules/wizard.js`, `js/push.js`, `js/restart.js`, `js/style.js`, `js/theme.js`, `js/viewer.js`, `js/welcome.js` |
| `js/artifact.js` | `js/modules/trace.js` |
| `js/backup.js` | `js/modules/plugins.js`, `js/modules/status.js` |
| `js/beat.js` | `js/modules/dj_player.js` |
| `js/bus.js` | `js/beat.js`, `js/main.js`, `js/modules/advanced.js`, `js/modules/alerts.js`, `js/modules/autonomy_box.js`, `js/modules/chat.js`, `js/modules/ciso.js`, `js/modules/dj.js`, `js/modules/dj_player.js`, `js/modules/interpret.js`, `js/modules/notifications.js`, `js/modules/plugin_slot.js`, `js/modules/plugins.js`, `js/modules/project_files.js`, `js/modules/projects.js`, `js/modules/security.js`, `js/modules/security_defence.js`, `js/modules/security_firewalls.js`, `js/modules/security_trace.js`, `js/modules/sky.js`, `js/modules/social.js`, `js/modules/today.js`, `js/modules/trace.js`, `js/modules/users.js`, `js/share.js`, `js/welcome.js` |
| `js/calendar_alerts.js` | `js/modules/chat.js` |
| `js/cards.js` | `js/modules/updates.js` |
| `js/dates.js` | `js/modules/astro_collim.js`, `js/modules/astro_nights.js`, `js/modules/astro_sky.js`, `js/modules/settings.js`, `js/style.js` |
| `js/diet.js` | `js/modules/care_diet.js`, `js/modules/chat.js` |
| `js/dom.js` | `js/artifact.js`, `js/backup.js`, `js/calendar_alerts.js`, `js/cards.js`, `js/dates.js`, `js/diet.js`, `js/icon_picker.js`, `js/main.js`, `js/md.js`, `js/modules/accounts.js`, `js/modules/accounts_services.js`, `js/modules/advanced.js`, `js/modules/alerts.js`, `js/modules/approvals.js`, `js/modules/astro.js`, `js/modules/astro_advice.js`, `js/modules/astro_collim.js`, `js/modules/astro_collim_live.js`, `js/modules/astro_collim_pc.js`, `js/modules/astro_imaging.js`, `js/modules/astro_live.js`, `js/modules/astro_mount.js`, `js/modules/astro_nights.js`, `js/modules/astro_shoot.js`, `js/modules/astro_sky.js`, `js/modules/astro_tuner.js`, `js/modules/aurorafw.js`, `js/modules/autonomy.js`, `js/modules/autonomy_box.js`, `js/modules/brain.js`, `js/modules/bugreport.js`, `js/modules/calendar.js`, `js/modules/calendar_form.js`, `js/modules/calendar_grid.js`, `js/modules/care.js`, `js/modules/care_diet.js`, `js/modules/care_doctor.js`, `js/modules/care_values.js`, `js/modules/chat.js`, `js/modules/chat_actions.js`, `js/modules/chat_anon.js`, `js/modules/chat_media.js`, `js/modules/chat_menu.js`, `js/modules/ciso.js`, `js/modules/composer.js`, `js/modules/consoles.js`, `js/modules/deductions_box.js`, `js/modules/diary.js`, `js/modules/dj.js`, `js/modules/dj_deck.js`, `js/modules/dj_player.js`, `js/modules/dj_radio.js`, `js/modules/dj_set.js`, `js/modules/dj_spotify.js`, `js/modules/dj_styles.js`, `js/modules/dreams.js`, `js/modules/expenses.js`, `js/modules/firewall.js`, `js/modules/fw_pick.js`, `js/modules/guide.js`, `js/modules/harvest_plan.js`, `js/modules/harvester.js`, `js/modules/home.js`, `js/modules/home_auto.js`, `js/modules/home_scenes.js`, `js/modules/hosts.js`, `js/modules/https.js`, `js/modules/ideas.js`, `js/modules/import.js`, `js/modules/interpret.js`, `js/modules/keys.js`, `js/modules/mask_view.js`, `js/modules/memory.js`, `js/modules/metrics.js`, `js/modules/models.js`, `js/modules/models_choice.js`, `js/modules/models_custom.js`, `js/modules/models_mode.js`, `js/modules/notifications.js`, `js/modules/people.js`, `js/modules/phone_app.js`, `js/modules/plugin_slot.js`, `js/modules/plugins.js`, `js/modules/project_conduct.js`, `js/modules/project_docs.js`, `js/modules/project_files.js`, `js/modules/project_page.js`, `js/modules/project_papers.js`, `js/modules/project_plan.js`, `js/modules/project_policy.js`, `js/modules/project_print.js`, `js/modules/project_render.js`, `js/modules/project_sim.js`, `js/modules/project_talk.js`, `js/modules/project_term.js`, `js/modules/projects.js`, `js/modules/reports.js`, `js/modules/routines.js`, `js/modules/routines_templates.js`, `js/modules/runs.js`, `js/modules/security.js`, `js/modules/security_defence.js`, `js/modules/security_edge.js`, `js/modules/security_egress_page.js`, `js/modules/security_firewalls.js`, `js/modules/security_map.js`, `js/modules/security_quiet.js`, `js/modules/security_trace.js`, `js/modules/security_watch.js`, `js/modules/settings.js`, `js/modules/settings_form.js`, `js/modules/social.js`, `js/modules/social_video.js`, `js/modules/status.js`, `js/modules/synapses.js`, `js/modules/today.js`, `js/modules/today_edit.js`, `js/modules/today_pages.js`, `js/modules/trace.js`, `js/modules/updates.js`, `js/modules/uploads.js`, `js/modules/ups.js`, `js/modules/usage.js`, `js/modules/users.js`, `js/modules/wizard.js`, `js/mood.js`, `js/nav_find.js`, `js/restart.js`, `js/share.js`, `js/theme.js`, `js/viewer.js`, `js/welcome.js` |
| `js/i18n.js` | `js/artifact.js`, `js/backup.js`, `js/calendar_alerts.js`, `js/cards.js`, `js/dates.js`, `js/diet.js`, `js/icon_picker.js`, `js/main.js`, `js/modules/accounts.js`, `js/modules/accounts_services.js`, `js/modules/advanced.js`, `js/modules/alerts.js`, `js/modules/approvals.js`, `js/modules/astro.js`, `js/modules/astro_advice.js`, `js/modules/astro_collim.js`, `js/modules/astro_collim_live.js`, `js/modules/astro_collim_pc.js`, `js/modules/astro_imaging.js`, `js/modules/astro_live.js`, `js/modules/astro_mount.js`, `js/modules/astro_mount3d.js`, `js/modules/astro_nights.js`, `js/modules/astro_shoot.js`, `js/modules/astro_sky.js`, `js/modules/astro_tuner.js`, `js/modules/aurorafw.js`, `js/modules/autonomy.js`, `js/modules/autonomy_box.js`, `js/modules/brain.js`, `js/modules/bugreport.js`, `js/modules/calendar.js`, `js/modules/calendar_form.js`, `js/modules/calendar_grid.js`, `js/modules/care.js`, `js/modules/care_diet.js`, `js/modules/care_doctor.js`, `js/modules/care_values.js`, `js/modules/chat.js`, `js/modules/chat_actions.js`, `js/modules/chat_anon.js`, `js/modules/chat_media.js`, `js/modules/chat_menu.js`, `js/modules/ciso.js`, `js/modules/consoles.js`, `js/modules/deductions_box.js`, `js/modules/diary.js`, `js/modules/dj.js`, `js/modules/dj_deck.js`, `js/modules/dj_player.js`, `js/modules/dj_radio.js`, `js/modules/dj_set.js`, `js/modules/dj_spotify.js`, `js/modules/dj_styles.js`, `js/modules/dreams.js`, `js/modules/expenses.js`, `js/modules/firewall.js`, `js/modules/guide.js`, `js/modules/harvest_plan.js`, `js/modules/harvester.js`, `js/modules/home.js`, `js/modules/home_auto.js`, `js/modules/home_scenes.js`, `js/modules/hosts.js`, `js/modules/https.js`, `js/modules/ideas.js`, `js/modules/ideas_page.js`, `js/modules/import.js`, `js/modules/interpret.js`, `js/modules/keys.js`, `js/modules/mask_view.js`, `js/modules/memory.js`, `js/modules/metrics.js`, `js/modules/models.js`, `js/modules/models_choice.js`, `js/modules/models_custom.js`, `js/modules/models_mode.js`, `js/modules/notifications.js`, `js/modules/people.js`, `js/modules/phone_app.js`, `js/modules/plugin_slot.js`, `js/modules/plugins.js`, `js/modules/project_conduct.js`, `js/modules/project_docs.js`, `js/modules/project_files.js`, `js/modules/project_page.js`, `js/modules/project_papers.js`, `js/modules/project_plan.js`, `js/modules/project_policy.js`, `js/modules/project_print.js`, `js/modules/project_render.js`, `js/modules/project_sim.js`, `js/modules/project_talk.js`, `js/modules/project_term.js`, `js/modules/projects.js`, `js/modules/reports.js`, `js/modules/routines.js`, `js/modules/routines_templates.js`, `js/modules/runs.js`, `js/modules/security.js`, `js/modules/security_defence.js`, `js/modules/security_edge.js`, `js/modules/security_egress_page.js`, `js/modules/security_firewalls.js`, `js/modules/security_map.js`, `js/modules/security_quiet.js`, `js/modules/security_trace.js`, `js/modules/security_watch.js`, `js/modules/settings.js`, `js/modules/settings_form.js`, `js/modules/social.js`, `js/modules/social_video.js`, `js/modules/status.js`, `js/modules/synapses.js`, `js/modules/today.js`, `js/modules/today_edit.js`, `js/modules/today_pages.js`, `js/modules/trace.js`, `js/modules/updates.js`, `js/modules/uploads.js`, `js/modules/ups.js`, `js/modules/usage.js`, `js/modules/users.js`, `js/modules/wizard.js`, `js/mood.js`, `js/nav_find.js`, `js/restart.js`, `js/share.js`, `js/theme.js`, `js/viewer.js`, `js/welcome.js` |
| `js/icon_picker.js` | `js/modules/consoles.js` |
| `js/main.js` | `index.html` |
| `js/md.js` | `js/modules/care.js`, `js/modules/diary.js`, `js/modules/dreams.js`, `js/modules/expenses.js`, `js/modules/guide.js`, `js/modules/memory.js`, `js/modules/plugins.js`, `js/modules/project_files.js`, `js/modules/project_page.js`, `js/modules/project_sim.js`, `js/modules/project_talk.js`, `js/modules/reports.js`, `js/modules/routines.js`, `js/modules/security.js`, `js/modules/trace.js`, `js/modules/wizard.js` |
| `js/modules.js` | `js/main.js` |
| `js/modules/accounts.js` | `js/modules.js` |
| `js/modules/accounts_services.js` | `js/modules/accounts.js` |
| `js/modules/advanced.js` | `js/modules.js` |
| `js/modules/alerts.js` | `js/modules.js` |
| `js/modules/approvals.js` | `js/modules.js`, `js/modules/chat.js`, `js/modules/plugins.js`, `js/modules/social.js` |
| `js/modules/astro.js` | `js/modules.js`, `js/modules/today.js` |
| `js/modules/astro_advice.js` | `js/modules/astro.js` |
| `js/modules/astro_collim.js` | `js/modules/astro.js` |
| `js/modules/astro_collim_live.js` | `js/modules/astro_collim.js` |
| `js/modules/astro_collim_pc.js` | `js/modules/astro_collim_live.js` |
| `js/modules/astro_imaging.js` | `js/modules/astro.js` |
| `js/modules/astro_live.js` | `js/modules/astro.js` |
| `js/modules/astro_mount.js` | `js/modules/astro_live.js` |
| `js/modules/astro_mount3d.js` | `js/modules/astro_mount.js` |
| `js/modules/astro_nights.js` | `js/modules/astro.js` |
| `js/modules/astro_shoot.js` | `js/modules/astro_live.js` |
| `js/modules/astro_sky.js` | `js/modules/astro.js` |
| `js/modules/astro_tuner.js` | `js/modules/astro_live.js` |
| `js/modules/aurorafw.js` | `js/modules.js` |
| `js/modules/autonomy.js` | `js/modules.js` |
| `js/modules/autonomy_box.js` | `js/modules/approvals.js`, `js/modules/aurorafw.js`, `js/modules/ciso.js`, `js/modules/diary.js`, `js/modules/firewall.js`, `js/modules/harvester.js`, `js/modules/home.js`, `js/modules/import.js`, `js/modules/plugins.js`, `js/modules/security.js`, `js/modules/security_edge.js`, `js/modules/security_egress_page.js`, `js/modules/social.js`, `js/modules/synapses.js`, `js/modules/updates.js` |
| `js/modules/brain.js` | `js/modules.js` |
| `js/modules/brain_3d.js` | `js/modules/brain.js` |
| `js/modules/brain_gray.js` | `js/modules/brain.js` |
| `js/modules/bugreport.js` | `js/modules.js` |
| `js/modules/calendar.js` | `js/modules.js` |
| `js/modules/calendar_form.js` | `js/modules/calendar.js`, `js/modules/calendar_grid.js` |
| `js/modules/calendar_grid.js` | `js/modules/calendar.js` |
| `js/modules/care.js` | `js/modules.js` |
| `js/modules/care_diet.js` | `js/modules/care.js` |
| `js/modules/care_doctor.js` | `js/modules/care.js` |
| `js/modules/care_values.js` | `js/modules/care.js` |
| `js/modules/chat.js` | `js/modules.js` |
| `js/modules/chat_actions.js` | `js/modules/chat.js`, `js/modules/chat_anon.js` |
| `js/modules/chat_anon.js` | `js/modules.js` |
| `js/modules/chat_media.js` | `js/modules/chat.js` |
| `js/modules/chat_menu.js` | `js/modules/chat.js` |
| `js/modules/chat_think.js` | `js/modules/chat.js`, `js/modules/chat_menu.js` |
| `js/modules/ciso.js` | `js/modules.js` |
| `js/modules/composer.js` | `js/modules/chat.js`, `js/modules/chat_anon.js`, `js/modules/project_conduct.js` |
| `js/modules/consoles.js` | `js/modules.js` |
| `js/modules/deductions_box.js` | `js/modules/synapses.js` |
| `js/modules/diary.js` | `js/modules.js` |
| `js/modules/dj.js` | `js/modules.js` |
| `js/modules/dj_deck.js` | `js/modules/dj.js` |
| `js/modules/dj_milk.js` | `js/modules/dj_player.js` |
| `js/modules/dj_player.js` | `js/modules/dj.js` |
| `js/modules/dj_radio.js` | `js/modules/dj.js` |
| `js/modules/dj_set.js` | `js/modules/dj.js`, `js/modules/dj_player.js` |
| `js/modules/dj_spotify.js` | `js/modules/dj.js` |
| `js/modules/dj_styles.js` | `js/modules/dj.js` |
| `js/modules/dreams.js` | `js/modules.js` |
| `js/modules/expenses.js` | `js/modules.js` |
| `js/modules/firewall.js` | `js/modules.js` |
| `js/modules/fw_pick.js` | `js/modules/firewall.js`, `js/modules/security_defence.js` |
| `js/modules/guide.js` | `js/modules.js` |
| `js/modules/harvest_plan.js` | `js/modules/harvester.js` |
| `js/modules/harvester.js` | `js/modules.js` |
| `js/modules/home.js` | `js/modules.js` |
| `js/modules/home_auto.js` | `js/modules/home.js` |
| `js/modules/home_scenes.js` | `js/modules/home.js` |
| `js/modules/hosts.js` | `js/modules.js` |
| `js/modules/https.js` | `js/modules.js` |
| `js/modules/ideas.js` | `js/modules/ideas_page.js` |
| `js/modules/ideas_page.js` | `js/modules.js` |
| `js/modules/import.js` | `js/modules.js` |
| `js/modules/interpret.js` | `js/modules.js` |
| `js/modules/keys.js` | `js/modules.js` |
| `js/modules/mask_view.js` | `js/modules/accounts.js`, `js/modules/social.js` |
| `js/modules/memory.js` | `js/modules.js` |
| `js/modules/metrics.js` | `js/modules.js` |
| `js/modules/models.js` | `js/modules.js` |
| `js/modules/models_choice.js` | `js/modules/models.js`, `js/welcome.js` |
| `js/modules/models_custom.js` | `js/modules/models.js` |
| `js/modules/models_mode.js` | `js/modules/models.js`, `js/modules/models_choice.js` |
| `js/modules/models_presets.js` | `js/modules/models_choice.js`, `js/welcome.js` |
| `js/modules/notifications.js` | `js/modules.js` |
| `js/modules/people.js` | `js/modules.js` |
| `js/modules/phone_app.js` | `js/modules.js` |
| `js/modules/plugin_slot.js` | `js/modules/astro.js`, `js/modules/calendar.js`, `js/modules/care.js`, `js/modules/diary.js`, `js/modules/dj.js`, `js/modules/expenses.js`, `js/modules/https.js`, `js/modules/projects.js`, `js/modules/routines.js`, `js/modules/security_edge.js`, `js/modules/security_firewalls.js`, `js/modules/social.js`, `js/modules/status.js` |
| `js/modules/plugins.js` | `js/modules.js`, `js/modules/plugin_slot.js` |
| `js/modules/project_conduct.js` | `js/modules/project_page.js` |
| `js/modules/project_docs.js` | `js/modules/project_files.js`, `js/modules/project_page.js` |
| `js/modules/project_files.js` | `js/modules/project_page.js` |
| `js/modules/project_page.js` | `js/modules/projects.js` |
| `js/modules/project_papers.js` | `js/modules/projects.js` |
| `js/modules/project_plan.js` | `js/modules/project_page.js` |
| `js/modules/project_policy.js` | `js/modules/project_page.js`, `js/modules/projects.js` |
| `js/modules/project_print.js` | `js/modules/project_page.js` |
| `js/modules/project_render.js` | `js/modules/project_page.js` |
| `js/modules/project_render_gl.js` | `js/modules/project_render.js` |
| `js/modules/project_sim.js` | `js/modules/project_page.js` |
| `js/modules/project_sim_expr.js` | `js/modules/project_sim.js` |
| `js/modules/project_talk.js` | `js/modules/project_conduct.js` |
| `js/modules/project_term.js` | `js/modules/project_page.js` |
| `js/modules/projects.js` | `js/modules.js`, `js/modules/today.js` |
| `js/modules/reports.js` | `js/modules.js` |
| `js/modules/routines.js` | `js/modules.js` |
| `js/modules/routines_templates.js` | `js/modules/routines.js` |
| `js/modules/runs.js` | `js/modules.js` |
| `js/modules/security.js` | `js/modules.js`, `js/modules/security_defence_page.js`, `js/modules/security_out_page.js`, `js/modules/security_watch_page.js` |
| `js/modules/security_defence.js` | `js/modules/security.js` |
| `js/modules/security_defence_page.js` | `js/modules.js` |
| `js/modules/security_edge.js` | `js/modules.js` |
| `js/modules/security_egress_page.js` | `js/modules.js` |
| `js/modules/security_firewalls.js` | `js/modules.js` |
| `js/modules/security_map.js` | `js/modules/security_defence.js` |
| `js/modules/security_out_page.js` | `js/modules.js` |
| `js/modules/security_quiet.js` | `js/modules/security.js` |
| `js/modules/security_trace.js` | `js/modules.js` |
| `js/modules/security_watch.js` | `js/modules/security.js` |
| `js/modules/security_watch_page.js` | `js/modules.js` |
| `js/modules/settings.js` | `js/modules.js` |
| `js/modules/settings_form.js` | `js/modules/accounts.js`, `js/modules/astro.js`, `js/modules/astro_imaging.js`, `js/modules/plugins.js`, `js/modules/ups.js` |
| `js/modules/sky.js` | `js/modules.js` |
| `js/modules/social.js` | `js/modules.js`, `js/modules/social_video.js` |
| `js/modules/social_video.js` | `js/modules/social.js` |
| `js/modules/status.js` | `js/modules.js` |
| `js/modules/synapses.js` | `js/modules.js` |
| `js/modules/today.js` | `js/modules.js`, `js/modules/advanced.js` |
| `js/modules/today_edit.js` | `js/modules/advanced.js`, `js/modules/today.js` |
| `js/modules/today_pages.js` | `js/modules/today.js`, `js/modules/today_edit.js` |
| `js/modules/trace.js` | `js/modules/chat.js`, `js/modules/chat_anon.js` |
| `js/modules/updates.js` | `js/modules.js` |
| `js/modules/uploads.js` | `js/modules.js` |
| `js/modules/ups.js` | `js/modules.js` |
| `js/modules/usage.js` | `js/modules.js` |
| `js/modules/users.js` | `js/modules.js` |
| `js/modules/wizard.js` | `js/modules/settings_form.js` |
| `js/mood.js` | `js/modules/alerts.js`, `js/modules/status.js` |
| `js/nav_find.js` | `js/main.js` |
| `js/push.js` | `js/modules/alerts.js`, `js/modules/notifications.js` |
| `js/qr.js` | `js/main.js`, `js/modules/https.js`, `js/modules/users.js` |
| `js/restart.js` | `js/modules/autonomy.js`, `js/modules/autonomy_box.js`, `js/modules/firewall.js`, `js/modules/harvester.js`, `js/modules/models_choice.js`, `js/modules/models_mode.js`, `js/modules/settings.js`, `js/modules/settings_form.js`, `js/modules/updates.js`, `js/modules/wizard.js` |
| `js/share.js` | `js/modules/chat_media.js`, `js/modules/diary.js`, `js/modules/dreams.js` |
| `js/stack.js` | `js/main.js` |
| `js/style.js` | `js/main.js`, `js/modules/advanced.js`, `js/modules/today.js`, `js/welcome.js` |
| `js/theme.js` | `js/main.js`, `js/style.js`, `js/welcome.js` |
| `js/vad.js` | `js/modules/chat.js`, `js/modules/chat_media.js`, `js/modules/interpret.js` |
| `js/viewer.js` | `js/modules/chat.js`, `js/modules/chat_media.js`, `js/modules/diary.js`, `js/modules/dreams.js`, `js/modules/routines.js`, `js/modules/trace.js`, `js/modules/uploads.js` |
| `js/voice.js` | `js/main.js`, `js/modules/chat.js`, `js/modules/chat_actions.js`, `js/modules/chat_media.js`, `js/modules/chat_menu.js`, `js/modules/interpret.js` |
| `js/welcome.js` | `js/main.js` |
| `sw.js` | `js/main.js` |

## API routes: who calls them

Callers are found by the route's path in the WebUI, the scripts and the plugins; a route with nobody is called from outside (a phone, a client, a webhook) or by a path built at run time.

| route | served by | called by |
|---|---|---|
| POST `/v1/aurora/devices` | `api/access.py` | `aurora/sys_assist.py`, `script/svc_api.py`, `webui/js/api.js`, `webui/js/modules/settings.js` |
| GET `/v1/aurora/devices` | `api/access.py` | `aurora/sys_assist.py`, `script/svc_api.py`, `webui/js/api.js`, `webui/js/modules/settings.js` |
| DELETE `/v1/aurora/devices/{device_id}` | `api/access.py` | `script/svc_api.py`, `webui/js/modules/settings.js` |
| POST `/v1/aurora/logout` | `api/access.py` | `aurora/sys_assist.py`, `script/svc_api.py`, `webui/js/main.js`, `webui/js/modules/settings.js` |
| GET `/v1/aurora/accounts` | `api/accounts.py` | `webui/js/modules/accounts.js` |
| POST `/v1/aurora/accounts` | `api/accounts.py` | `webui/js/modules/accounts.js` |
| POST `/v1/aurora/accounts/{account_id}/login` | `api/accounts.py` | `webui/js/modules/accounts.js`, `webui/js/modules/accounts_services.js` |
| POST `/v1/aurora/accounts/{account_id}/code` | `api/accounts.py` | `webui/js/modules/accounts.js`, `webui/js/modules/accounts_services.js` |
| GET `/v1/aurora/accounts/{account_id}/status` | `api/accounts.py` | `webui/js/modules/accounts.js`, `webui/js/modules/accounts_services.js` |
| DELETE `/v1/aurora/accounts/{account_id}` | `api/accounts.py` | `webui/js/modules/accounts.js`, `webui/js/modules/accounts_services.js` |
| PUT `/v1/aurora/accounts/policy` | `api/accounts.py` | `webui/js/modules/accounts.js` |
| POST `/v1/aurora/accounts/services/try` | `api/accounts.py` | `webui/js/modules/accounts_services.js` |
| POST `/v1/aurora/accounts/services` | `api/accounts.py` | `webui/js/modules/accounts_services.js` |
| DELETE `/v1/aurora/accounts/services/{sid}` | `api/accounts.py` | `webui/js/modules/accounts_services.js` |
| GET `/v1/aurora/accounts/mask` | `api/accounts.py` | `webui/js/modules/accounts.js` |
| POST `/v1/aurora/activity` | `api/activity.py` | `script/svc_api.py`, `script/svc_backup.py`, `script/svc_harvester.py`, `script/svc_rem.py`, `webui/js/modules/runs.js` |
| GET `/v1/aurora/activity` | `api/activity.py` | `script/svc_api.py`, `script/svc_backup.py`, `script/svc_harvester.py`, `script/svc_rem.py`, `webui/js/modules/runs.js` |
| GET `/v1/aurora/activity/stream` | `api/activity.py` | `webui/js/modules/alerts.js`, `webui/js/modules/brain.js`, `webui/js/modules/chat.js` |
| GET `/v1/aurora/logs` | `api/activity.py` | `script/svc_api.py` |
| GET `/v1/aurora/logs/{component}` | `api/activity.py` | — |
| GET `/v1/aurora/runs/{run_id}/record` | `api/activity.py` | `script/bench_agi.py`, `script/bench_memory_days.py`, `script/bench_quality.py`, `script/shadow_seed.py`, `script/svc_api.py`, `webui/js/api.js` |
| GET `/v1/aurora/soak` | `api/activity.py` | `webui/js/modules/status.js` |
| GET `/v1/aurora/video/status` | `api/activity.py` | `script/shadow_seed.py`, `webui/js/modules/chat.js` |
| GET `/v1/aurora/health` | `api/activity.py` | `script/svc_api.py`, `webui/js/modules/alerts.js`, `webui/js/modules/status.js`, `webui/js/modules/today.js` |
| GET `/v1/aurora/answers/stats` | `api/activity.py` | `webui/js/modules/status.js` |
| GET `/v1/aurora/memory/about-me` | `api/activity.py` | `script/mem_prune.py`, `webui/js/modules/memory.js` |
| DELETE `/v1/aurora/memory/about-me` | `api/activity.py` | `script/mem_prune.py`, `webui/js/modules/memory.js` |
| DELETE `/v1/aurora/memory/conversation` | `api/activity.py` | `script/mem_prune.py` |
| DELETE `/v1/aurora/memory/reflection` | `api/activity.py` | `script/mem_prune.py` |
| GET `/v1/aurora/reflections` | `api/activity.py` | `script/svc_api.py`, `webui/js/modules/diary.js`, `webui/js/modules/reports.js`, `webui/js/modules/today_pages.js` |
| POST `/v1/aurora/agent` | `api/agents.py` | `script/bench_repair.py`, `script/svc_api.py`, `webui/js/modules/chat.js` |
| GET `/v1/aurora/plugins/signature` | `api/agents.py` | `webui/js/modules/plugins.js` |
| GET `/v1/aurora/plugins` | `api/agents.py` | `script/svc_api.py`, `webui/js/main.js`, `webui/js/modules/approvals.js`, `webui/js/modules/plugin_slot.js`, `webui/js/modules/plugins.js`, `webui/js/modules/routines.js`, `webui/js/modules/today.js` |
| PUT `/v1/aurora/plugins/{name}/away` | `api/agents.py` | `script/svc_api.py`, `webui/js/modules/expenses.js`, `webui/js/modules/plugins.js` |
| POST `/v1/aurora/plugins/{name}/icon` | `api/agents.py` | `script/svc_api.py`, `webui/js/modules/expenses.js`, `webui/js/modules/plugins.js` |
| POST `/v1/aurora/plugins/{name}/{action}` | `api/agents.py` | `script/svc_api.py`, `webui/js/modules/expenses.js`, `webui/js/modules/plugins.js` |
| GET `/v1/aurora/plugins-trash` | `api/agents.py` | `webui/js/modules/plugins.js` |
| POST `/v1/aurora/plugins-trash/{item}/purge` | `api/agents.py` | `webui/js/modules/plugins.js` |
| POST `/v1/aurora/plugins-trash/{item}/restore` | `api/agents.py` | `webui/js/modules/plugins.js` |
| GET `/v1/aurora/plugins/{name}/icon` | `api/agents.py` | `script/svc_api.py`, `webui/js/modules/expenses.js`, `webui/js/modules/plugins.js` |
| POST `/v1/aurora/services/restart` | `api/agents.py` | `webui/js/modules/autonomy.js`, `webui/js/modules/autonomy_box.js`, `webui/js/modules/firewall.js`, `webui/js/modules/harvester.js`, `webui/js/restart.js` |
| POST `/v1/aurora/plugins/{name}/try/{tool}` | `api/agents.py` | `script/svc_api.py`, `webui/js/modules/expenses.js`, `webui/js/modules/plugins.js` |
| GET `/v1/aurora/approvals` | `api/agents.py` | `script/bench_repair.py`, `script/svc_api.py`, `webui/js/modules/alerts.js`, `webui/js/modules/approvals.js`, `webui/js/modules/plugins.js`, `webui/js/modules/social.js`, `webui/js/modules/today.js` |
| GET `/v1/aurora/approvals/stats` | `api/agents.py` | `webui/js/modules/approvals.js` |
| POST `/v1/aurora/approvals/{approval_id}/{decision}` | `api/agents.py` | `script/bench_repair.py`, `script/svc_api.py`, `webui/js/modules/approvals.js`, `webui/js/modules/social.js` |
| POST `/v1/aurora/rem/repair` | `api/agents.py` | `script/svc_api.py` |
| GET `/v1/aurora/assist` | `api/assist.py` | `script/svc_api.py`, `webui/js/modules/users.js` |
| POST `/v1/aurora/assist/grant` | `api/assist.py` | `aurora/sys_assist.py`, `webui/js/modules/users.js` |
| POST `/v1/aurora/assist/revoke` | `api/assist.py` | `aurora/sys_assist.py`, `webui/js/modules/users.js` |
| POST `/v1/aurora/assist/enter` | `api/assist.py` | `webui/js/modules/users.js` |
| POST `/v1/aurora/assist/leave` | `api/assist.py` | `webui/js/main.js` |
| GET `/v1/aurora/astro` | `api/astro.py` | `webui/js/modules/astro.js` |
| GET `/v1/aurora/astro/script` | `api/astro.py` | `webui/js/modules/astro.js` |
| POST `/v1/aurora/astro/files` | `api/astro.py` | `webui/js/modules/astro.js` |
| DELETE `/v1/aurora/astro/files/{name}` | `api/astro.py` | `webui/js/modules/astro.js` |
| GET `/v1/aurora/astro/nights` | `api/astro.py` | `webui/js/modules/astro_nights.js` |
| GET `/v1/aurora/astro/advice` | `api/astro.py` | `webui/js/modules/astro_advice.js` |
| PUT `/v1/aurora/astro/advice` | `api/astro.py` | `webui/js/modules/astro_advice.js` |
| GET `/v1/aurora/astro/imaging` | `api/astro.py` | `webui/js/modules/astro_imaging.js` |
| PUT `/v1/aurora/astro/imaging` | `api/astro.py` | `webui/js/modules/astro_imaging.js` |
| GET `/v1/aurora/astro/sky` | `api/astro.py` | `webui/js/modules/astro_sky.js`, `webui/js/modules/today.js` |
| GET `/v1/aurora/astro/sky/thumb` | `api/astro.py` | `webui/js/modules/astro_sky.js`, `webui/js/modules/today.js` |
| POST `/v1/aurora/astro/sky/sequence` | `api/astro.py` | `webui/js/modules/astro_sky.js` |
| GET `/v1/aurora/astro/sky/sequence/file` | `api/astro.py` | `webui/js/modules/astro_sky.js` |
| POST `/v1/aurora/astro/sky/sequence/send` | `api/astro.py` | `webui/js/modules/astro_sky.js` |
| GET `/v1/aurora/astro/live` | `api/astro.py` | `webui/js/modules/astro_live.js` |
| GET `/v1/aurora/astro/nina` | `api/astro.py` | `webui/js/modules/astro_mount.js` |
| GET `/v1/aurora/astro/nina/mount` | `api/astro.py` | `webui/js/modules/astro_mount.js` |
| GET `/v1/aurora/astro/autoguide` | `api/astro.py` | `webui/js/modules/astro_tuner.js` |
| PUT `/v1/aurora/astro/autoguide` | `api/astro.py` | `webui/js/modules/astro_tuner.js` |
| GET `/v1/aurora/astro/collimation` | `api/astro.py` | `webui/js/modules/astro_collim.js` |
| PUT `/v1/aurora/astro/collimation/scope` | `api/astro.py` | `webui/js/modules/astro_collim_live.js` |
| POST `/v1/aurora/astro/collimation/photo` | `api/astro.py` | `webui/js/modules/astro_collim.js`, `webui/js/modules/astro_collim_live.js` |
| POST `/v1/aurora/astro/collimation/star` | `api/astro.py` | `webui/js/modules/astro_collim.js` |
| GET `/v1/aurora/astro/collimation/stars` | `api/astro.py` | `webui/js/modules/astro_collim.js` |
| POST `/v1/aurora/astro/camera/key` | `api/astro_cam.py` | `webui/js/modules/astro_collim_pc.js` |
| GET `/v1/aurora/astro/camera/bundle` | `api/astro_cam.py` | `webui/js/modules/astro_collim_pc.js` |
| GET `/v1/aurora/astro/camera` | `api/astro_cam.py` | `webui/js/modules/astro_collim_pc.js` |
| PUT `/v1/aurora/astro/camera` | `api/astro_cam.py` | `webui/js/modules/astro_collim_pc.js` |
| GET `/v1/aurora/astro/camera/frame` | `api/astro_cam.py` | — |
| GET `/v1/aurora/astro/camera/stream` | `api/astro_cam.py` | `webui/js/modules/astro_collim_live.js` |
| POST `/v1/aurora/astro/camera/pc` | `api/astro_cam.py` | `sys/plugins/astro/astro_camera.py` |
| POST `/v1/aurora/astro/camera/push` | `api/astro_cam.py` | `sys/plugins/astro/astro_camera.py` |
| GET `/v1/aurora/autonomy` | `api/autonomy.py` | `webui/js/modules/autonomy.js`, `webui/js/modules/autonomy_box.js` |
| PUT `/v1/aurora/autonomy` | `api/autonomy.py` | `webui/js/modules/autonomy.js`, `webui/js/modules/autonomy_box.js` |
| PUT `/v1/aurora/autonomy/may-choose` | `api/autonomy.py` | `webui/js/modules/autonomy.js` |
| GET `/v1/aurora/backup` | `api/backup.py` | `webui/js/backup.js` |
| POST `/v1/aurora/backup/mount` | `api/backup.py` | `webui/js/backup.js` |
| GET `/v1/aurora/backup/snapshots` | `api/backup.py` | `webui/js/backup.js` |
| POST `/v1/aurora/backup/run` | `api/backup.py` | `webui/js/backup.js` |
| POST `/v1/aurora/bugreport` | `api/bugreport.py` | `webui/js/modules/bugreport.js` |
| GET `/v1/aurora/ideas` | `api/bugreport.py` | `webui/js/modules/ideas.js`, `webui/js/modules/today_pages.js` |
| POST `/v1/aurora/ideas` | `api/bugreport.py` | `webui/js/modules/ideas.js`, `webui/js/modules/today_pages.js` |
| PUT `/v1/aurora/ideas/{iid}` | `api/bugreport.py` | `webui/js/modules/ideas.js` |
| POST `/v1/aurora/ideas/{iid}/issue` | `api/bugreport.py` | `webui/js/modules/ideas.js` |
| GET `/v1/aurora/bugreports` | `api/bugreport.py` | `webui/js/modules/bugreport.js` |
| GET `/v1/aurora/bugreports/{name}` | `api/bugreport.py` | — |
| GET `/v1/aurora/calendar` | `api/calendar.py` | `webui/js/modules/calendar.js`, `webui/js/modules/today.js` |
| GET `/v1/aurora/calendar/people` | `api/calendar.py` | `webui/js/modules/calendar_form.js` |
| POST `/v1/aurora/calendar/items` | `api/calendar.py` | `webui/js/modules/calendar_form.js` |
| GET `/v1/aurora/calendar/items/{iid}` | `api/calendar.py` | `webui/js/modules/calendar.js`, `webui/js/modules/calendar_form.js` |
| PUT `/v1/aurora/calendar/items/{iid}` | `api/calendar.py` | `webui/js/modules/calendar.js`, `webui/js/modules/calendar_form.js` |
| GET `/v1/aurora/calendar/invites` | `api/calendar.py` | `webui/js/modules/calendar.js` |
| POST `/v1/aurora/calendar/items/{iid}/rsvp` | `api/calendar.py` | `webui/js/modules/calendar.js`, `webui/js/modules/calendar_form.js` |
| DELETE `/v1/aurora/calendar/items/{iid}` | `api/calendar.py` | `webui/js/modules/calendar.js`, `webui/js/modules/calendar_form.js` |
| GET `/v1/aurora/calendar/pending` | `api/calendar.py` | `webui/js/calendar_alerts.js` |
| POST `/v1/aurora/calendar/answer` | `api/calendar.py` | `webui/js/calendar_alerts.js` |
| GET `/v1/aurora/calendar/export.ics` | `api/calendar.py` | `webui/js/modules/calendar.js` |
| POST `/v1/aurora/calendar/import` | `api/calendar.py` | `webui/js/modules/calendar.js` |
| POST `/v1/aurora/call` | `api/call.py` | `webui/js/modules/phone_app.js` |
| POST `/v1/aurora/call/dial` | `api/call.py` | `webui/js/modules/chat.js` |
| POST `/v1/aurora/call/{call_id}/decline` | `api/call.py` | `webui/js/modules/chat.js` |
| WEBSOCKET `/v1/aurora/call/{call_id}/audio` | `api/call.py` | `webui/js/modules/chat.js` |
| GET `/v1/aurora/health/values` | `api/care.py` | `webui/js/modules/care_values.js` |
| POST `/v1/aurora/health/values/read/{doc_id}` | `api/care.py` | `webui/js/modules/care.js` |
| PUT `/v1/aurora/health/values/{vid}` | `api/care.py` | `webui/js/modules/care.js`, `webui/js/modules/care_values.js` |
| DELETE `/v1/aurora/health/values/{vid}` | `api/care.py` | `webui/js/modules/care.js`, `webui/js/modules/care_values.js` |
| GET `/v1/aurora/care/doctors` | `api/care.py` | `webui/js/modules/care_doctor.js` |
| PUT `/v1/aurora/care/doctors` | `api/care.py` | `webui/js/modules/care_doctor.js` |
| GET `/v1/aurora/care` | `api/care.py` | `webui/js/modules/care.js` |
| POST `/v1/aurora/care/{area}` | `api/care.py` | `webui/js/modules/care.js`, `webui/js/modules/care_doctor.js` |
| POST `/v1/aurora/care/{area}/note` | `api/care.py` | `webui/js/modules/care.js`, `webui/js/modules/care_doctor.js` |
| GET `/v1/aurora/care/{area}/{iid}` | `api/care.py` | `webui/js/modules/care.js`, `webui/js/modules/care_doctor.js` |
| GET `/v1/aurora/care/{area}/{iid}/file` | `api/care.py` | `webui/js/modules/care.js`, `webui/js/modules/care_doctor.js` |
| DELETE `/v1/aurora/care/{area}/{iid}` | `api/care.py` | `webui/js/modules/care.js`, `webui/js/modules/care_doctor.js` |
| GET `/v1/aurora/diet` | `api/diet.py` | `webui/js/diet.js`, `webui/js/modules/care_diet.js` |
| POST `/v1/aurora/diet/process` | `api/diet.py` | `webui/js/modules/care_diet.js` |
| POST `/v1/aurora/diet/choice` | `api/diet.py` | `webui/js/diet.js` |
| DELETE `/v1/aurora/diet/choice/{cid}` | `api/diet.py` | `webui/js/diet.js` |
| GET `/v1/aurora/diet/pending` | `api/diet.py` | `webui/js/diet.js` |
| GET `/v1/aurora/dj` | `api/dj.py` | `webui/js/modules/dj.js`, `webui/js/modules/dj_player.js`, `webui/js/modules/dj_radio.js`, `webui/js/modules/dj_set.js`, `webui/js/modules/dj_styles.js`, `webui/js/modules/today_pages.js` |
| PUT `/v1/aurora/dj/playlists` | `api/dj.py` | `webui/js/modules/dj_player.js` |
| POST `/v1/aurora/dj/tracks` | `api/dj.py` | `webui/js/modules/dj_player.js` |
| DELETE `/v1/aurora/dj/{kind}/{name}` | `api/dj.py` | `webui/js/modules/dj.js`, `webui/js/modules/dj_player.js`, `webui/js/modules/dj_radio.js`, `webui/js/modules/dj_set.js`, `webui/js/modules/dj_styles.js` |
| GET `/v1/aurora/dj/{kind}/{name}` | `api/dj.py` | `webui/js/modules/dj.js`, `webui/js/modules/dj_player.js`, `webui/js/modules/dj_radio.js`, `webui/js/modules/dj_set.js`, `webui/js/modules/dj_styles.js` |
| POST `/v1/aurora/dj/make` | `api/dj.py` | `webui/js/modules/dj.js` |
| POST `/v1/aurora/dj/learn` | `api/dj.py` | `webui/js/modules/dj_radio.js` |
| POST `/v1/aurora/dj/learn/stop` | `api/dj.py` | `webui/js/modules/dj_radio.js` |
| GET `/v1/aurora/dj/learn` | `api/dj.py` | `webui/js/modules/dj_radio.js` |
| GET `/v1/aurora/dj/styles/{sid}/preview` | `api/dj.py` | `webui/js/modules/dj_styles.js` |
| DELETE `/v1/aurora/dj/styles/{sid}` | `api/dj.py` | `webui/js/modules/dj_styles.js` |
| POST `/v1/aurora/dj/set` | `api/dj.py` | `webui/js/modules/dj_set.js` |
| GET `/v1/aurora/dj-timeline/{name}` | `api/dj.py` | `webui/js/modules/dj_set.js` |
| POST `/v1/aurora/dj/song` | `api/dj.py` | `webui/js/modules/dj_player.js`, `webui/js/modules/dj_set.js` |
| GET `/v1/aurora/dj-song/{name}` | `api/dj.py` | `webui/js/modules/dj_player.js` |
| PUT `/v1/aurora/dj-song/{name}` | `api/dj.py` | `webui/js/modules/dj_player.js` |
| POST `/v1/aurora/dj/listening` | `api/dj.py` | `webui/js/modules/dj_player.js` |
| POST `/v1/aurora/documents/pdf` | `api/documents.py` | `webui/js/modules/trace.js` |
| GET `/v1/aurora/documents` | `api/documents.py` | `webui/js/modules/uploads.js` |
| GET `/v1/aurora/documents/{name}` | `api/documents.py` | `aurora/doc_preview.py`, `aurora/sys_routines.py`, `aurora/sys_uploads.py`, `sys/plugins/documents/plugin.json`, `webui/js/modules/trace.js` |
| DELETE `/v1/aurora/documents/{name}` | `api/documents.py` | `aurora/doc_preview.py`, `aurora/sys_routines.py`, `aurora/sys_uploads.py`, `sys/plugins/documents/plugin.json`, `webui/js/modules/trace.js` |
| GET `/v1/aurora/security/edge` | `api/edge.py` | `webui/js/modules/security_edge.js` |
| GET `/v1/aurora/security/edge/culprits` | `api/edge.py` | `webui/js/modules/security_edge.js` |
| POST `/v1/aurora/security/edge/block` | `api/edge.py` | `webui/js/modules/security_edge.js` |
| POST `/v1/aurora/security/edge/unblock` | `api/edge.py` | `webui/js/modules/security_edge.js` |
| GET `/v1/aurora/security/firewalls` | `api/firewalls.py` | `webui/js/main.js`, `webui/js/modules/security_firewalls.js` |
| PUT `/v1/aurora/security/firewalls/{fid}` | `api/firewalls.py` | `webui/js/modules/security_firewalls.js` |
| DELETE `/v1/aurora/security/firewalls/{fid}` | `api/firewalls.py` | `webui/js/modules/security_firewalls.js` |
| POST `/v1/aurora/security/firewalls/{fid}/connect` | `api/firewalls.py` | `webui/js/modules/security_firewalls.js` |
| GET `/v1/aurora/forge` | `api/forge.py` | `script/svc_api.py`, `webui/js/modules/plugins.js` |
| POST `/v1/aurora/forge/tick` | `api/forge.py` | `script/svc_api.py`, `script/svc_rem.py` |
| PUT `/v1/aurora/harvester/domains` | `api/harvester.py` | `script/svc_api.py`, `webui/js/modules/harvester.js` |
| GET `/v1/aurora/harvester` | `api/harvester.py` | `script/svc_api.py`, `webui/js/modules/harvester.js` |
| POST `/v1/aurora/harvester/{action}` | `api/harvester.py` | `script/svc_api.py`, `webui/js/modules/harvest_plan.js`, `webui/js/modules/harvester.js` |
| GET `/v1/aurora/home/devices` | `api/home.py` | `webui/js/modules/home.js`, `webui/js/modules/today.js`, `webui/js/welcome.js` |
| POST `/v1/aurora/home/service` | `api/home.py` | `webui/js/modules/home.js`, `webui/js/modules/today.js` |
| GET `/v1/aurora/home/camera/{entity_id}` | `api/home.py` | `webui/js/modules/home.js` |
| POST `/v1/aurora/home/look` | `api/home.py` | `webui/js/modules/home.js` |
| POST `/v1/aurora/home/agents/{device_id}` | `api/home.py` | `webui/js/modules/home.js` |
| GET `/v1/aurora/home/scenes` | `api/home.py` | `webui/js/modules/home_auto.js`, `webui/js/modules/home_scenes.js` |
| POST `/v1/aurora/home/scenes` | `api/home.py` | `webui/js/modules/home_auto.js`, `webui/js/modules/home_scenes.js` |
| POST `/v1/aurora/home/scenes/{name}/{action}` | `api/home.py` | `webui/js/modules/home_scenes.js` |
| GET `/v1/aurora/home/automations` | `api/home.py` | `webui/js/modules/home.js`, `webui/js/modules/home_auto.js` |
| POST `/v1/aurora/home/automations` | `api/home.py` | `webui/js/modules/home.js`, `webui/js/modules/home_auto.js` |
| POST `/v1/aurora/home/automations/{aid}/{action}` | `api/home.py` | `webui/js/modules/home_auto.js` |
| GET `/v1/aurora/https` | `api/https.py` | `webui/js/modules/https.js` |
| PUT `/v1/aurora/https/cert` | `api/https.py` | `webui/js/modules/https.js` |
| DELETE `/v1/aurora/https/cert` | `api/https.py` | `webui/js/modules/https.js` |
| PUT `/v1/aurora/https/names` | `api/https.py` | `webui/js/modules/https.js` |
| PUT `/v1/aurora/https/ports` | `api/https.py` | `webui/js/modules/https.js` |
| POST `/v1/aurora/sentinel/incident` | `api/incidents.py` | `script/svc_api.py`, `script/svc_sentinel.py` |
| GET `/v1/aurora/incidents` | `api/incidents.py` | `script/svc_api.py`, `webui/js/modules/alerts.js`, `webui/js/modules/security.js` |
| POST `/v1/aurora/incidents/archive-closed` | `api/incidents.py` | `webui/js/modules/security.js` |
| GET `/v1/aurora/security/scorecard` | `api/incidents.py` | `webui/js/modules/security.js` |
| POST `/v1/aurora/incidents/{incident_id}/verdict` | `api/incidents.py` | `script/svc_api.py`, `webui/js/modules/security.js`, `webui/js/modules/security_quiet.js` |
| GET `/v1/aurora/incidents/quiet` | `api/incidents.py` | `webui/js/modules/security_quiet.js` |
| POST `/v1/aurora/incidents/quiet` | `api/incidents.py` | `webui/js/modules/security_quiet.js` |
| POST `/v1/aurora/incidents/{incident_id}/close` | `api/incidents.py` | `script/svc_api.py`, `webui/js/modules/security.js`, `webui/js/modules/security_quiet.js` |
| POST `/v1/aurora/interpret` | `api/interpret.py` | `webui/js/modules/interpret.js` |
| GET `/v1/aurora/keys` | `api/keys.py` | `webui/js/modules/keys.js` |
| POST `/v1/aurora/keys/recovery` | `api/keys.py` | `webui/js/modules/keys.js` |
| POST `/v1/aurora/keys/recovery/check` | `api/keys.py` | `webui/js/modules/keys.js` |
| GET `/v1/aurora/domains` | `api/knowledge.py` | `script/kno_import.py`, `script/svc_api.py`, `webui/js/modules/import.js` |
| POST `/v1/aurora/import` | `api/knowledge.py` | `script/kno_import.py`, `script/svc_api.py`, `script/svc_harvester.py`, `script/vault_realign.py`, `webui/js/modules/import.js` |
| POST `/v1/aurora/solitons` | `api/knowledge.py` | `aurora/kno_dedup.py`, `script/kno_migrate_legacy.py`, `script/svc_api.py`, `script/svc_harvester.py` |
| DELETE `/v1/aurora/sources` | `api/knowledge.py` | `script/svc_api.py`, `script/vault_realign.py` |
| POST `/v1/aurora/memory/reset` | `api/knowledge.py` | `script/svc_api.py` |
| GET `/v1/aurora/history` | `api/knowledge.py` | `script/svc_api.py`, `webui/js/modules/chat.js` |
| GET `/v1/aurora/senses/devices` | `api/knowledge.py` | `script/svc_api.py`, `webui/js/modules/plugins.js` |
| POST `/v1/aurora/senses/{action}` | `api/knowledge.py` | `script/svc_api.py`, `webui/js/modules/chat.js`, `webui/js/modules/chat_media.js`, `webui/js/modules/plugins.js` |
| GET `/v1/aurora/features` | `api/knowledge.py` | `webui/js/modules/status.js` |
| GET `/v1/aurora/line` | `api/line.py` | `aurora/sys_line.py` |
| GET `/v1/aurora/models` | `api/models.py` | `script/svc_api.py`, `webui/js/modules/models.js`, `webui/js/welcome.js` |
| GET `/v1/aurora/models/media` | `api/models.py` | `webui/js/modules/models.js` |
| PUT `/v1/aurora/models/media` | `api/models.py` | `webui/js/modules/models.js` |
| GET `/v1/aurora/models/limits` | `api/models.py` | `webui/js/modules/models.js` |
| PUT `/v1/aurora/models/limits` | `api/models.py` | `webui/js/modules/models.js` |
| PUT `/v1/aurora/models/roles` | `api/models.py` | `script/svc_api.py`, `webui/js/modules/models.js`, `webui/js/modules/models_choice.js` |
| GET `/v1/aurora/models/modes` | `api/models.py` | `webui/js/modules/models_choice.js`, `webui/js/modules/models_mode.js`, `webui/js/welcome.js` |
| POST `/v1/aurora/models/mode` | `api/models.py` | `webui/js/modules/models_choice.js`, `webui/js/modules/models_mode.js` |
| POST `/v1/aurora/models/reasoner` | `api/models.py` | `webui/js/modules/models_mode.js` |
| GET `/v1/aurora/models/{provider}/list` | `api/models.py` | `script/svc_api.py`, `webui/js/modules/models.js`, `webui/js/modules/models_choice.js`, `webui/js/modules/models_custom.js`, `webui/js/modules/models_mode.js`, `webui/js/welcome.js` |
| GET `/v1/aurora/models/stats` | `api/models.py` | `webui/js/modules/models.js` |
| GET `/v1/aurora/models/custom` | `api/models_custom.py` | `webui/js/modules/models_custom.js` |
| GET `/v1/aurora/models/custom/inspect` | `api/models_custom.py` | `webui/js/modules/models_custom.js` |
| GET `/v1/aurora/models/custom/check` | `api/models_custom.py` | `webui/js/modules/models_custom.js` |
| POST `/v1/aurora/models/custom/download` | `api/models_custom.py` | `webui/js/modules/models_custom.js` |
| POST `/v1/aurora/models/custom/switch` | `api/models_custom.py` | `webui/js/modules/models_custom.js` |
| POST `/v1/aurora/models/custom/revert` | `api/models_custom.py` | `webui/js/modules/models_custom.js` |
| GET `/health` | `api/oai.py` | `aurora/mdl_image.py`, `aurora/mdl_llm.py`, `aurora/mdl_remote.py`, `aurora/sys_health.py`, `config/settings_schema.json`, `script/doc_charts.py`, `script/svc_api.py`, `script/svc_harvester.py`, `script/svc_models.py`, `script/svc_rem.py`, `script/sys_install_services.py`, `sys/plugins/health/plugin.json`, `webui/js/main.js`, `webui/js/modules/alerts.js`, `webui/js/modules/status.js`, `webui/js/modules/today.js`, `webui/js/restart.js` |
| GET `/v1/models` | `api/oai.py` | `aurora/aud_song.py`, `aurora/mdl_formats.py`, `script/svc_api.py`, `webui/js/main.js` |
| POST `/v1/chat/completions` | `api/oai.py` | `aurora/mdl_llm.py`, `script/svc_api.py` |
| POST `/v1/aurora/oauth/{provider}/start` | `api/oauth.py` | `webui/js/main.js`, `webui/js/modules/plugins.js` |
| POST `/v1/aurora/oauth/finish` | `api/oauth.py` | `webui/js/main.js` |
| GET `/v1/aurora/people` | `api/people.py` | `webui/js/modules/people.js` |
| PUT `/v1/aurora/people/me` | `api/people.py` | `webui/js/modules/people.js` |
| POST `/v1/aurora/people/me/bio` | `api/people.py` | `webui/js/modules/people.js` |
| DELETE `/v1/aurora/people/me/bio/{bid}` | `api/people.py` | `webui/js/modules/people.js` |
| POST `/v1/aurora/people/me/propose` | `api/people.py` | `webui/js/modules/people.js` |
| POST `/v1/aurora/people/me/proposals/{pid}` | `api/people.py` | `webui/js/modules/people.js` |
| POST `/v1/aurora/people/relations` | `api/people.py` | `webui/js/modules/people.js` |
| POST `/v1/aurora/people/relations/{rid}` | `api/people.py` | `webui/js/modules/people.js` |
| DELETE `/v1/aurora/people/relations/{rid}` | `api/people.py` | `webui/js/modules/people.js` |
| PUT `/v1/aurora/people/me/photo` | `api/people.py` | `webui/js/modules/people.js` |
| POST `/v1/aurora/people/me/avatar` | `api/people.py` | `webui/js/modules/people.js` |
| POST `/v1/aurora/people/me/picture` | `api/people.py` | `webui/js/modules/people.js` |
| GET `/v1/aurora/people/{user}/picture` | `api/people.py` | `aurora/sys_people.py`, `webui/js/modules/people.js` |
| GET `/v1/aurora/app` | `api/phone_app.py` | `webui/js/modules/phone_app.js` |
| GET `/v1/aurora/app/download` | `api/phone_app.py` | `webui/js/modules/phone_app.js` |
| GET `/v1/aurora/places` | `api/places.py` | `webui/js/modules/plugins.js` |
| GET `/v1/aurora/weather/next` | `api/places.py` | `webui/js/modules/metrics.js` |
| GET `/v1/aurora/power/hosts` | `api/power.py` | `webui/js/modules/hosts.js` |
| PUT `/v1/aurora/power/hosts/{hid}` | `api/power.py` | `webui/js/modules/hosts.js` |
| DELETE `/v1/aurora/power/hosts/{hid}` | `api/power.py` | `webui/js/modules/hosts.js` |
| GET `/v1/aurora/power/hosts/{hid}/setup` | `api/power.py` | `webui/js/modules/hosts.js` |
| POST `/v1/aurora/power/hosts/{hid}/{action}` | `api/power.py` | `webui/js/modules/hosts.js` |
| POST `/v1/aurora/security/firewalls/{fid}/console` | `api/power.py` | `webui/js/modules/security_firewalls.js` |
| POST `/v1/aurora/artifacts/open` | `api/preview.py` | `webui/js/artifact.js` |
| GET `/v1/aurora/preview` | `api/preview.py` | `webui/js/viewer.js` |
| GET `/v1/aurora/preview/page` | `api/preview.py` | `webui/js/modules/uploads.js`, `webui/js/viewer.js` |
| GET `/v1/aurora/projects` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/projects.js`, `webui/js/modules/today_pages.js` |
| GET `/v1/aurora/projects/github` | `api/projects.py` | `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/papers` | `api/projects.py` | `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/github/{owner}/{repo}/traffic` | `api/projects.py` | `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/tree` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/file` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/reports` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/log` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/preview` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/preview/{token}/{path:path}` | `api/projects.py` | `aurora/doc_artifact.py`, `aurora/net_https.py`, `script/svc_api.py`, `webui/js/artifact.js` |
| POST `/v1/aurora/projects` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/projects.js`, `webui/js/modules/today_pages.js` |
| POST `/v1/aurora/projects/{name}/save` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/policy` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| PUT `/v1/aurora/projects/{name}/policy` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/clone` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/terminal` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/terminal/{sid}/stream` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/terminal/{sid}/input` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| DELETE `/v1/aurora/projects/{name}/terminal/{sid}` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/conduct` | `api/projects_conduct.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/conduct` | `api/projects_conduct.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/conduct/{entry}/start` | `api/projects_conduct.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/conduct/{entry}/drop` | `api/projects_conduct.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/live` | `api/projects_conduct.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/talk` | `api/projects_conduct.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/talk` | `api/projects_conduct.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/talk/stop` | `api/projects_conduct.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/conductor/tools` | `api/projects_conduct.py` | — |
| POST `/v1/aurora/conductor/call` | `api/projects_conduct.py` | — |
| POST `/v1/aurora/projects/{name}/talk/new` | `api/projects_conduct.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/plan` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/plan` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| PUT `/v1/aurora/projects/{name}/plan` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/docs` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/docs` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/pdf` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/cad` | `api/projects_print.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/cad/{model}/print.zip` | `api/projects_print.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/scene` | `api/projects_view.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/cad/{model}/part/{k}.stl` | `api/projects_view.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/sims` | `api/projects_view.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/cover` | `api/projects_view.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| PUT `/v1/aurora/projects/{name}/cover` | `api/projects_view.py` | `script/svc_api.py`, `webui/js/modules/project_conduct.js`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_files.js`, `webui/js/modules/project_page.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_policy.js`, `webui/js/modules/project_print.js`, `webui/js/modules/project_render.js`, `webui/js/modules/project_sim.js`, `webui/js/modules/project_talk.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/radio` | `api/radio.py` | `webui/js/modules/dj_radio.js` |
| GET `/v1/aurora/radio/search` | `api/radio.py` | `webui/js/modules/dj_radio.js` |
| POST `/v1/aurora/radio/favourites` | `api/radio.py` | `webui/js/modules/dj_radio.js` |
| GET `/v1/aurora/radio/{sid}/stream` | `api/radio.py` | `aurora/aud_radio.py`, `webui/js/modules/dj_radio.js` |
| GET `/v1/aurora/rem/users` | `api/rem.py` | `script/svc_rem.py` |
| GET `/v1/aurora/mood` | `api/rem.py` | `webui/js/modules/alerts.js` |
| GET `/v1/aurora/rem/state` | `api/rem.py` | `script/svc_api.py`, `script/svc_rem.py`, `webui/js/modules/status.js` |
| POST `/v1/aurora/rem/{task}` | `api/rem.py` | `script/svc_api.py`, `script/svc_rem.py`, `webui/js/modules/status.js` |
| GET `/v1/aurora/dreams` | `api/rem.py` | `webui/js/modules/dreams.js`, `webui/js/modules/today.js` |
| GET `/v1/aurora/routines/advice` | `api/routine_advice.py` | `webui/js/modules/routines.js` |
| POST `/v1/aurora/routines/advice/review` | `api/routine_advice.py` | `webui/js/modules/routines.js` |
| POST `/v1/aurora/routines/advice/{aid}/{action}` | `api/routine_advice.py` | `webui/js/modules/routines.js` |
| GET `/v1/aurora/routines/templates` | `api/routine_advice.py` | `webui/js/modules/routines_templates.js` |
| POST `/v1/aurora/routines/templates/{pack}/apply` | `api/routine_advice.py` | `webui/js/modules/routines_templates.js` |
| POST `/v1/aurora/routines/templates` | `api/routine_advice.py` | `webui/js/modules/routines_templates.js` |
| DELETE `/v1/aurora/routines/templates/{pack}` | `api/routine_advice.py` | `webui/js/modules/routines_templates.js` |
| GET `/v1/aurora/routines` | `api/routines.py` | `script/svc_api.py`, `webui/js/modules/routines.js`, `webui/js/modules/today_pages.js` |
| POST `/v1/aurora/routines` | `api/routines.py` | `script/svc_api.py`, `webui/js/modules/routines.js`, `webui/js/modules/today_pages.js` |
| PUT `/v1/aurora/routines/{rid}` | `api/routines.py` | `script/svc_api.py`, `script/svc_rem.py`, `webui/js/modules/routines.js`, `webui/js/modules/routines_templates.js` |
| DELETE `/v1/aurora/routines/{rid}` | `api/routines.py` | `script/svc_api.py`, `script/svc_rem.py`, `webui/js/modules/routines.js`, `webui/js/modules/routines_templates.js` |
| POST `/v1/aurora/routines/{rid}/clone` | `api/routines.py` | `script/svc_api.py`, `script/svc_rem.py`, `webui/js/modules/routines.js`, `webui/js/modules/routines_templates.js` |
| POST `/v1/aurora/routines/{rid}/run` | `api/routines.py` | `script/svc_api.py`, `script/svc_rem.py`, `webui/js/modules/routines.js`, `webui/js/modules/routines_templates.js` |
| POST `/v1/aurora/routines/tick` | `api/routines.py` | `script/svc_api.py`, `script/svc_rem.py` |
| GET `/v1/aurora/notifications` | `api/routines.py` | `script/svc_api.py`, `webui/js/modules/notifications.js` |
| GET `/v1/aurora/notifications/history` | `api/routines.py` | `webui/js/modules/notifications.js` |
| PUT `/v1/aurora/notifications` | `api/routines.py` | `script/svc_api.py`, `webui/js/modules/notifications.js` |
| POST `/v1/aurora/update/apply` | `api/routines.py` | `webui/js/modules/updates.js` |
| GET `/v1/aurora/push` | `api/routines.py` | `script/svc_api.py`, `webui/js/push.js`, `webui/sw.js` |
| POST `/v1/aurora/push-ack` | `api/routines.py` | `webui/sw.js` |
| GET `/v1/aurora/push/delivery` | `api/routines.py` | `webui/js/modules/notifications.js` |
| POST `/v1/aurora/push/{action}` | `api/routines.py` | `script/svc_api.py`, `webui/js/modules/notifications.js`, `webui/js/push.js` |
| GET `/v1/aurora/images/{name}` | `api/routines.py` | `script/svc_api.py`, `webui/js/modules/diary.js`, `webui/js/modules/social.js` |
| GET `/v1/aurora/metrics` | `api/routines.py` | `script/svc_api.py`, `webui/js/modules/metrics.js` |
| POST `/v1/aurora/ask` | `api/runs.py` | `script/bench_agi.py`, `script/bench_memory_days.py`, `script/bench_public.py`, `script/bench_quality.py`, `script/shadow_seed.py`, `script/svc_api.py`, `webui/js/modules/chat.js`, `webui/js/modules/chat_anon.js` |
| POST `/v1/aurora/shadow/import` | `api/runs.py` | `script/shadow_seed.py` |
| POST `/v1/aurora/acquire` | `api/runs.py` | `script/svc_api.py`, `webui/js/modules/chat.js` |
| GET `/v1/aurora/runs` | `api/runs.py` | `script/bench_preflight.py`, `script/bench_repair.py`, `script/svc_api.py`, `script/svc_sentinel.py`, `webui/js/modules/brain.js`, `webui/js/modules/bugreport.js`, `webui/js/modules/runs.js`, `webui/js/modules/social_video.js` |
| GET `/v1/aurora/runs/{run_id}/events` | `api/runs.py` | `script/bench_agi.py`, `script/bench_memory_days.py`, `script/bench_quality.py`, `script/shadow_seed.py`, `script/svc_api.py`, `webui/js/api.js` |
| GET `/v1/aurora/chat/anon` | `api/runs.py` | `webui/js/modules/chat_anon.js` |
| POST `/v1/aurora/chat/anon` | `api/runs.py` | `webui/js/modules/chat_anon.js` |
| DELETE `/v1/aurora/chat/anon` | `api/runs.py` | `webui/js/modules/chat_anon.js` |
| GET `/v1/aurora/security/profile` | `api/security.py` | `webui/js/modules/security_watch.js` |
| POST `/v1/aurora/security/learn` | `api/security.py` | `webui/js/modules/security.js` |
| PUT `/v1/aurora/security/rules` | `api/security.py` | `webui/js/modules/security_watch.js` |
| GET `/v1/aurora/security/host` | `api/security.py` | `webui/js/modules/security_defence.js` |
| POST `/v1/aurora/security/host/unblock` | `api/security.py` | `webui/js/modules/aurorafw.js`, `webui/js/modules/security_defence.js` |
| GET `/v1/aurora/security/weekly` | `api/security.py` | `webui/js/modules/security_defence.js` |
| GET `/v1/aurora/security/netmap` | `api/security.py` | `webui/js/modules/security.js`, `webui/js/modules/security_defence.js` |
| POST `/v1/aurora/security/netmap/refresh` | `api/security.py` | `webui/js/modules/security_defence.js` |
| GET `/v1/aurora/security/netmap/graph` | `api/security.py` | `webui/js/modules/security_map.js` |
| GET `/v1/aurora/security/netmap/find` | `api/security.py` | `webui/js/modules/security_defence.js` |
| POST `/v1/aurora/security/firewall/test` | `api/security.py` | `webui/js/modules/security_defence.js` |
| GET `/v1/aurora/security/outbound` | `api/security.py` | `webui/js/modules/security_watch.js` |
| GET `/v1/aurora/security/defence` | `api/security.py` | `webui/js/modules/security.js`, `webui/js/modules/security_defence.js` |
| POST `/v1/aurora/security/defence/release` | `api/security.py` | `webui/js/modules/security_defence.js` |
| GET `/v1/aurora/security/egress` | `api/security.py` | `webui/js/modules/security.js`, `webui/js/modules/security_egress_page.js`, `webui/js/modules/today.js` |
| POST `/v1/aurora/security/egress-legit` | `api/security.py` | `webui/js/modules/security.js` |
| POST `/v1/aurora/security/egress-deny` | `api/security.py` | `webui/js/modules/security.js` |
| POST `/v1/aurora/security/block` | `api/security.py` | `webui/js/modules/security.js` |
| GET `/v1/aurora/security/trace` | `api/security.py` | `webui/js/modules/security_trace.js` |
| GET `/v1/aurora/security/geo` | `api/security.py` | — |
| POST `/v1/aurora/security/geo/update` | `api/security.py` | — |
| GET `/v1/aurora/security/audit` | `api/security_ciso.py` | `webui/js/modules/firewall.js` |
| GET `/v1/aurora/security/hunt` | `api/security_ciso.py` | `webui/js/modules/ciso.js` |
| GET `/v1/aurora/security/posture` | `api/security_ciso.py` | `webui/js/modules/ciso.js` |
| GET `/v1/aurora/security/changes` | `api/security_ciso.py` | `webui/js/modules/firewall.js` |
| POST `/v1/aurora/security/changes/plan` | `api/security_ciso.py` | `webui/js/modules/ciso.js`, `webui/js/modules/firewall.js` |
| POST `/v1/aurora/security/changes/ask` | `api/security_ciso.py` | `webui/js/modules/firewall.js` |
| POST `/v1/aurora/security/changes/{change_id}/{action}` | `api/security_ciso.py` | `webui/js/modules/ciso.js`, `webui/js/modules/firewall.js` |
| GET `/v1/aurora/security/aurora` | `api/security_ciso.py` | `webui/js/modules/aurorafw.js` |
| POST `/v1/aurora/security/aurora/block` | `api/security_ciso.py` | `webui/js/modules/aurorafw.js` |
| GET `/v1/aurora/security/docs` | `api/security_ciso.py` | `webui/js/modules/firewall.js` |
| GET `/v1/aurora/social` | `api/social.py` | `script/svc_api.py`, `webui/js/modules/social.js`, `webui/js/modules/today_pages.js` |
| POST `/v1/aurora/social/draft` | `api/social.py` | `script/svc_api.py`, `webui/js/modules/social.js` |
| GET `/v1/aurora/social/privacy` | `api/social.py` | `webui/js/modules/social.js` |
| POST `/v1/aurora/social/check` | `api/social.py` | `webui/js/modules/social.js` |
| POST `/v1/aurora/social/publish` | `api/social.py` | `script/svc_api.py`, `webui/js/modules/social.js` |
| GET `/v1/aurora/social/stories` | `api/social.py` | `webui/js/modules/social_video.js` |
| GET `/v1/aurora/social/stories/{stamp}/video` | `api/social.py` | `webui/js/modules/social_video.js` |
| POST `/v1/aurora/social/story` | `api/social.py` | `webui/js/modules/social_video.js` |
| GET `/v1/aurora/synapses` | `api/synapses.py` | `webui/js/modules/status.js`, `webui/js/modules/synapses.js` |
| POST `/v1/aurora/synapses/grow` | `api/synapses.py` | `script/svc_rem.py` |
| POST `/v1/aurora/synapses/level2` | `api/synapses.py` | `script/svc_rem.py`, `webui/js/modules/synapses.js` |
| GET `/v1/aurora/synapses/list` | `api/synapses.py` | `webui/js/modules/synapses.js` |
| PUT `/v1/aurora/synapses/link` | `api/synapses.py` | `webui/js/modules/synapses.js` |
| GET `/v1/aurora/synapses/concepts` | `api/synapses.py` | `webui/js/modules/synapses.js` |
| GET `/v1/aurora/deductions` | `api/synapses.py` | `webui/js/modules/deductions_box.js` |
| PUT `/v1/aurora/deductions/{did}` | `api/synapses.py` | `webui/js/modules/deductions_box.js` |
| POST `/v1/aurora/deductions/{did}/pdf` | `api/synapses.py` | `webui/js/modules/deductions_box.js` |
| POST `/v1/aurora/deductions/round` | `api/synapses.py` | `webui/js/modules/deductions_box.js` |
| GET `/v1/aurora/status` | `api/system.py` | `script/svc_api.py`, `webui/js/modules/status.js` |
| GET `/v1/aurora/settings` | `api/system.py` | `script/svc_api.py`, `sys/plugins/dropbox/authorize.py`, `sys/plugins/tiktok/authorize.py`, `webui/js/modules/care_diet.js`, `webui/js/modules/firewall.js`, `webui/js/modules/harvester.js`, `webui/js/modules/mask_view.js`, `webui/js/modules/settings.js`, `webui/js/modules/settings_form.js`, `webui/js/modules/updates.js`, `webui/js/modules/users.js`, `webui/js/modules/wizard.js`, `webui/js/welcome.js` |
| POST `/v1/aurora/settings/factory` | `api/system.py` | `webui/js/modules/settings.js` |
| GET `/v1/aurora/factory` | `api/system.py` | `webui/js/modules/settings.js` |
| POST `/v1/aurora/factory/mind` | `api/system.py` | `webui/js/modules/settings.js` |
| PUT `/v1/aurora/settings` | `api/system.py` | `script/svc_api.py`, `sys/plugins/dropbox/authorize.py`, `sys/plugins/tiktok/authorize.py`, `webui/js/modules/care_diet.js`, `webui/js/modules/firewall.js`, `webui/js/modules/harvester.js`, `webui/js/modules/mask_view.js`, `webui/js/modules/settings.js`, `webui/js/modules/settings_form.js`, `webui/js/modules/updates.js`, `webui/js/modules/users.js`, `webui/js/modules/wizard.js`, `webui/js/welcome.js` |
| GET `/v1/aurora/ups` | `api/system.py` | `webui/js/modules/security_firewalls.js`, `webui/js/modules/ups.js` |
| GET `/v1/aurora/debug/memory` | `api/system.py` | — |
| GET `/v1/aurora/consoles` | `api/system.py` | `webui/js/modules/consoles.js` |
| POST `/v1/aurora/consoles` | `api/system.py` | `webui/js/modules/consoles.js` |
| PUT `/v1/aurora/consoles/{cid}` | `api/system.py` | `webui/js/modules/consoles.js` |
| DELETE `/v1/aurora/consoles/{cid}` | `api/system.py` | `webui/js/modules/consoles.js` |
| GET `/v1/aurora/today/news` | `api/today.py` | `webui/js/modules/today.js` |
| GET `/v1/aurora/today/research` | `api/today.py` | `webui/js/modules/today.js` |
| GET `/v1/aurora/today/hello` | `api/today.py` | `webui/js/modules/today.js` |
| GET `/v1/aurora/today/publications` | `api/today.py` | `webui/js/modules/today.js` |
| GET `/v1/aurora/update` | `api/updates.py` | `script/svc_api.py`, `webui/js/modules/today_pages.js`, `webui/js/modules/updates.js` |
| GET `/v1/aurora/commands` | `api/updates.py` | `webui/js/cards.js` |
| POST `/v1/aurora/commands/{card}/verify` | `api/updates.py` | `webui/js/cards.js` |
| POST `/v1/aurora/update/check` | `api/updates.py` | `script/svc_rem.py`, `webui/js/modules/updates.js` |
| GET `/v1/aurora/uploads` | `api/uploads.py` | `script/svc_api.py`, `webui/js/modules/uploads.js` |
| GET `/v1/aurora/uploads/{uid}` | `api/uploads.py` | `aurora/doc_artifact.py`, `aurora/doc_preview.py`, `aurora/sys_trash.py`, `aurora/sys_uploads.py`, `script/svc_api.py`, `script/svc_rem.py`, `webui/js/modules/trace.js`, `webui/js/modules/uploads.js` |
| DELETE `/v1/aurora/uploads/{uid}` | `api/uploads.py` | `aurora/doc_artifact.py`, `aurora/doc_preview.py`, `aurora/sys_trash.py`, `aurora/sys_uploads.py`, `script/svc_api.py`, `script/svc_rem.py`, `webui/js/modules/trace.js`, `webui/js/modules/uploads.js` |
| GET `/v1/aurora/trash` | `api/uploads.py` | `webui/js/modules/uploads.js` |
| POST `/v1/aurora/trash/{tid}/restore` | `api/uploads.py` | `webui/js/modules/uploads.js` |
| DELETE `/v1/aurora/trash/{tid}` | `api/uploads.py` | `webui/js/modules/uploads.js` |
| POST `/v1/aurora/uploads/purge` | `api/uploads.py` | `aurora/sys_trash.py`, `script/svc_api.py`, `script/svc_rem.py` |
| GET `/v1/aurora/usage` | `api/usage.py` | `webui/js/modules/today.js`, `webui/js/modules/usage.js` |
| POST `/v1/aurora/login` | `api/users.py` | `aurora/sys_assist.py`, `script/bench_memory_days.py`, `webui/js/main.js` |
| GET `/v1/aurora/me` | `api/users.py` | `script/bench_memory_days.py`, `webui/js/main.js`, `webui/js/modules/plugin_slot.js`, `webui/js/modules/plugins.js`, `webui/js/modules/routines.js`, `webui/js/modules/settings.js`, `webui/js/modules/users.js` |
| PUT `/v1/aurora/me/prefs` | `api/users.py` | `webui/js/dates.js`, `webui/js/modules/today_edit.js`, `webui/js/style.js`, `webui/js/theme.js` |
| POST `/v1/aurora/me/welcomed` | `api/users.py` | `aurora/sys_assist.py`, `webui/js/welcome.js` |
| POST `/v1/aurora/me/password` | `api/users.py` | `aurora/sys_assist.py`, `webui/js/modules/users.js` |
| POST `/v1/aurora/me/totp` | `api/users.py` | `aurora/sys_assist.py`, `webui/js/modules/users.js` |
| GET `/v1/aurora/me/keys` | `api/users.py` | `aurora/sys_assist.py`, `webui/js/modules/users.js` |
| POST `/v1/aurora/me/keys` | `api/users.py` | `aurora/sys_assist.py`, `webui/js/modules/users.js` |
| DELETE `/v1/aurora/me/keys/{key_id}` | `api/users.py` | `webui/js/modules/users.js` |
| GET `/v1/aurora/users` | `api/users.py` | `webui/js/modules/users.js` |
| GET `/v1/aurora/users/permissions` | `api/users.py` | `webui/js/modules/users.js` |
| PUT `/v1/aurora/users/permissions` | `api/users.py` | `webui/js/modules/users.js` |
| PUT `/v1/aurora/users/cloud` | `api/users.py` | `webui/js/modules/users.js` |
| POST `/v1/aurora/users` | `api/users.py` | `webui/js/modules/users.js` |
| POST `/v1/aurora/users/{name}/password` | `api/users.py` | `webui/js/modules/users.js` |
| POST `/v1/aurora/users/{name}/totp-reset` | `api/users.py` | `webui/js/modules/users.js` |
| DELETE `/v1/aurora/users/{name}` | `api/users.py` | `webui/js/modules/users.js` |
| GET `/v1/aurora/tts` | `api/voice.py` | `webui/js/voice.js` |
| POST `/v1/aurora/tts` | `api/voice.py` | `webui/js/voice.js` |

Modules nobody in the code imports: 0; routes nobody in the repository names: 8 of 430.
