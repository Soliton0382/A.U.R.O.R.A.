# Call map

Generated from the code by `sys/core/script/doc_callmap.py` (`--check` in publish.sh): who starts each script, who imports each module, who calls each API route. What each file does is in MODULE_MAP.md. A file nobody calls is listed as such: a tool run by hand, a route of an external client, or code to remove.

## Scripts: what starts them

| script | started, imported or named by |
|---|---|
| `bench_agi.py` | `script/bench_edge.py`, `script/bench_learn.py`, `script/bench_memory_days.py`, `script/bench_public.py` |
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
| `bench_image.py` | by hand |
| `bench_learn.py` | by hand |
| `bench_memory_days.py` | `script/bench_agi.py` |
| `bench_preflight.py` | by hand |
| `bench_public.py` | `script/bench_compare.py`, `script/bench_edge.py`, `script/bench_learn.py`, `script/bench_public_data.py`, `script/bench_router.py` |
| `bench_public_data.py` | `script/bench_public.py` |
| `bench_quality.py` | `script/bench_agi.py`, `script/bench_honesty.py`, `script/bench_memory_days.py`, `script/bench_public.py` |
| `bench_repair.py` | `aurora/api/agents.py`, `script/bench_agi.py` |
| `bench_retrieval.py` | `script/bench_vault_diag.py` |
| `bench_router.py` | by hand |
| `bench_vault_diag.py` | by hand |
| `dev_changelog.py` | `script/publish.sh` |
| `dev_license_headers.py` | by hand |
| `dev_privacy_scan.py` | `script/dev_publish.sh` |
| `dev_publish.sh` | `script/dev_privacy_scan.py`, `script/publish.sh` |
| `doc_callmap.py` | its own timer (--schedule), `script/dev_publish.sh` |
| `doc_charts.py` | `script/doc_figures.py` |
| `doc_figures.py` | by hand |
| `doc_plugins.py` | by hand |
| `doc_times.py` | `script/dev_publish.sh` |
| `img_ai.py` | `aurora/mdl_image.py` |
| `img_paint.py` | `aurora/mdl_image.py` |
| `kno_import.py` | by hand |
| `kno_migrate_legacy.py` | by hand |
| `plg_run.py` | `aurora/plg_deps.py`, `script/doc_plugins.py`, `sys/plugins/patent/plugin.json`, `sys/plugins/qr/plugin.json`, `sys/plugins/qr/server.py` |
| `publish.sh` | `aurora/agt_loop.py`, `aurora/api/routines.py`, `aurora/api/security_ciso.py`, `aurora/api/social.py`, `aurora/kno_social.py`, `aurora/kno_story_auto.py`, `aurora/sec_detonate.py`, `aurora/sec_fwwrite.py`, `aurora/sys_approvals.py`, `aurora/sys_routines.py`, `aurora/sys_social_guard.py`, `config/routine_templates.json`, `config/settings_schema.json`, `script/dev_license_headers.py`, `script/dev_privacy_scan.py`, `script/dev_publish.sh`, `script/doc_times.py`, `script/shadow_seed.py`, `script/svc_api.py`, `sys/plugins/facebook/plugin.json`, `sys/plugins/facebook/server.py`, `sys/plugins/instagram/server.py`, `sys/plugins/mastodon/plugin.json`, `sys/plugins/projects/plugin.json`, `sys/plugins/security/plugin.json`, `sys/plugins/tiktok/server.py`, `webui/i18n/en_US.json`, `webui/js/modules/firewall.js`, `webui/js/modules/social.js` |
| `shadow_seed.py` | its own timer (--schedule), `aurora/api/runs.py`, `aurora/kno_answer.py`, `aurora/kno_shadow.py`, `script/svc_api.py`, `script/sys_domains.py` |
| `story_intro_make.py` | `aurora/kno_story.py` |
| `story_music_fetch.py` | `config/story_music.json` |
| `svc_api.py` | `aurora/agt_change.py`, `aurora/api/__init__.py`, `script/sys_install_services.py` |
| `svc_backup.py` | `aurora/sys_health.py`, `config/settings_schema.json`, `script/sys_doctor.py`, `script/sys_install_services.py`, `script/sys_users_migrate.py`, `sys/plugins/backup/plugin.json`, `sys/plugins/backup/server.py` |
| `svc_harvester.py` | `aurora/agt_change.py`, `script/sys_install_services.py` |
| `svc_llm.py` | `aurora/agt_change.py`, `script/sys_install_services.py` |
| `svc_models.py` | `aurora/agt_change.py`, `script/sys_install_services.py` |
| `svc_rem.py` | `aurora/agt_change.py`, `script/sys_install_services.py` |
| `svc_sentinel.py` | `script/sys_install_services.py` |
| `sys_backup_retime.py` | its own timer (--schedule), `script/sys_install_services.py` |
| `sys_calibrate.py` | `install.sh` |
| `sys_cloud_setup.py` | `install.sh` |
| `sys_commands_write.py` | by hand |
| `sys_doctor.py` | `install.sh` |
| `sys_domains.py` | `install.sh` |
| `sys_env_sync.py` | `aurora/sys_config.py`, `aurora/sys_formats.py`, `install.sh`, `script/dev_publish.sh`, `script/sys_doctor.py`, `script/sys_restore.py` |
| `sys_ethics_sign.py` | `aurora/agt_forge.py`, `aurora/api/agents.py`, `aurora/mdl_modes.py`, `aurora/mdl_router.py`, `aurora/sys_cloud_consent.py`, `aurora/sys_ethics.py`, `aurora/sys_update.py`, `config/commands.json`, `install.sh`, `script/dev_license_headers.py`, `script/publish.sh`, `script/sys_doctor.py`, `script/sys_relocate.sh` |
| `sys_factory_reset.py` | `aurora/api/system.py`, `aurora/sys_reset.py`, `script/sys_install_services.py` |
| `sys_github_mcp_install.sh` | `install.sh`, `sys/plugins/github/plugin.json` |
| `sys_install_services.py` | its own timer (--schedule), `aurora/api/backup.py`, `aurora/api/system.py`, `aurora/net_https.py`, `install.sh`, `script/sys_relocate.sh`, `webui/i18n/en_US.json`, `webui/i18n/it_IT.json` |
| `sys_model_check.py` | by hand |
| `sys_models_fetch.py` | `aurora/mdl_video.py`, `aurora/sys_features.py`, `config/models.json`, `install.sh`, `script/sys_tts_install.sh`, `script/sys_tts_qwen_install.sh` |
| `sys_nas_mount.py` | `aurora/sys_backup.py`, `script/sys_install_services.py` |
| `sys_nvidia.sh` | `install.sh` |
| `sys_profile.py` | `aurora/mdl_custom.py`, `aurora/sys_features.py`, `install.sh`, `script/sys_calibrate.py`, `script/sys_model_check.py` |
| `sys_ready.py` | `install.sh` |
| `sys_relocate.sh` | by hand |
| `sys_restore.py` | `aurora/api/backup.py` |
| `sys_tts_install.sh` | `aurora/mdl_tts.py`, `aurora/sys_capabilities.py`, `aurora/sys_features.py`, `config/settings_schema.json`, `install.sh` |
| `sys_tts_qwen_install.sh` | `aurora/sys_features.py` |
| `sys_users_migrate.py` | `aurora/api/users.py`, `aurora/sys_users_layout.py`, `aurora/sys_users_mode.py`, `install.sh` |
| `tts_qwen_worker.py` | `aurora/mdl_tts.py` |
| `vault_realign.py` | `aurora/kno_vault_audit.py` |
| `vid_ai.py` | `aurora/mdl_video.py` |

## Library modules: who imports them

Tests are counted apart: a module imported only by tests is not used by Aurora.

| module | imported by (code) | tests |
|---|---|---|
| `aurora` | `agt_change`, `agt_forge`, `agt_forge_data`, `agt_loop`, `agt_loop_make`, `agt_react`, `api.access`, `api.accounts`, `api.activity`, `api.agents`, `api.autonomy`, `api.backup`, `api.bugreport`, `api.calendar`, `api.care`, `api.core`, `api.core_route`, `api.diet`, `api.dj`, `api.documents`, `api.forge`, `api.harvester`, `api.home`, `api.https`, `api.incidents`, `api.knowledge`, `api.models`, `api.models_custom`, `api.oauth`, `api.preview`, `api.projects`, `api.projects_plan`, `api.rem`, `api.routine_advice`, `api.routines`, `api.runs`, `api.security`, `api.security_ciso`, `api.social`, `api.synapses`, `api.system`, `api.tunnel`, `api.updates`, `api.uploads`, `api.users`, `api.voice`, `aud_deck`, `aud_dj`, `cal_external`, `cal_store`, `cal_text`, `doc_artifact`, `doc_pdf`, `doc_preview`, `hlt_diet`, `hlt_doctor`, `hlt_labs`, `hlt_store`, `hom_devices`, `hom_scenes`, `kno_acquire`, `kno_acquire_more`, `kno_answer`, `kno_attach`, `kno_deduce`, `kno_dedup`, `kno_docs`, `kno_followup`, `kno_grid`, `kno_harvest`, `kno_harvest_plan`, `kno_ingest`, `kno_lessons`, `kno_mood`, `kno_morning`, `kno_read`, `kno_rem`, `kno_review`, `kno_self`, `kno_shadow`, `kno_social`, `kno_sources`, `kno_split`, `kno_stages`, `kno_story`, `kno_story_auto`, `kno_study`, `kno_synapse`, `kno_synapse2`, `kno_think`, `kno_trail`, `kno_train`, `kno_vault_audit`, `kno_video`, `kno_web`, `mdl_accounts`, `mdl_budget`, `mdl_cloud`, `mdl_custom`, `mdl_embedder`, `mdl_formats`, `mdl_image`, `mdl_llm`, `mdl_media`, `mdl_modes`, `mdl_remote`, `mdl_reranker`, `mdl_router`, `mdl_services`, `mdl_stt`, `mdl_tts`, `mdl_video`, `net_cfwaf`, `net_cloudflare`, `net_geo`, `net_https`, `net_trace`, `plg_access`, `plg_host`, `plg_sandbox`, `plg_shadow`, `plg_trash`, `prj_browse`, `prj_docs`, `prj_plan`, `prj_reports`, `prj_run`, `prj_term`, `script/bench_common.py`, `script/bench_domain_assign.py`, `script/bench_domains.py`, `script/bench_followup.py`, `script/bench_forge.py`, `script/bench_honeypot.py`, `script/bench_image.py`, `script/bench_learn.py`, `script/bench_preflight.py`, `script/bench_public.py`, `script/bench_quality.py`, `script/bench_repair.py`, `script/bench_retrieval.py`, `script/bench_router.py`, `script/bench_vault_diag.py`, `script/dev_license_headers.py`, `script/dev_privacy_scan.py`, `script/img_ai.py`, `script/img_paint.py`, `script/kno_import.py`, `script/kno_migrate_legacy.py`, `script/shadow_seed.py`, `script/story_intro_make.py`, `script/story_music_fetch.py`, `script/svc_api.py`, `script/svc_backup.py`, `script/svc_harvester.py`, `script/svc_llm.py`, `script/svc_models.py`, `script/svc_rem.py`, `script/svc_sentinel.py`, `script/sys_backup_retime.py`, `script/sys_calibrate.py`, `script/sys_cloud_setup.py`, `script/sys_commands_write.py`, `script/sys_doctor.py`, `script/sys_domains.py`, `script/sys_env_sync.py`, `script/sys_ethics_sign.py`, `script/sys_factory_reset.py`, `script/sys_install_services.py`, `script/sys_model_check.py`, `script/sys_nas_mount.py`, `script/sys_ready.py`, `script/sys_restore.py`, `script/sys_users_migrate.py`, `script/vault_realign.py`, `script/vid_ai.py`, `sec_audit`, `sec_baseline`, `sec_defence`, `sec_detonate`, `sec_fwapi`, `sec_fwconf`, `sec_fwdocs`, `sec_fwplan`, `sec_fwport`, `sec_fwwrite`, `sec_hostaudit`, `sec_hostfw`, `sec_hunt`, `sec_incidents`, `sec_intel`, `sec_linkcheck`, `sec_mask`, `sec_netmap`, `sec_outbound`, `sec_privacy`, `sec_profile`, `sec_report`, `sec_rules`, `sec_scorecard`, `sec_shared`, `sns_av`, `sns_clock`, `sns_weather`, `sol_index`, `sol_lexical`, `sol_reader`, `sol_search`, `sol_vault`, `sol_writer`, `sys/plugins/backup/server.py`, `sys/plugins/cad/server.py`, `sys/plugins/calendar/server.py`, `sys/plugins/cloud/server.py`, `sys/plugins/cloudflare/server.py`, `sys/plugins/diary/server.py`, `sys/plugins/dj/server.py`, `sys/plugins/documents/server.py`, `sys/plugins/dropbox/authorize.py`, `sys/plugins/dropbox/server.py`, `sys/plugins/email_diag/server.py`, `sys/plugins/expenses/server.py`, `sys/plugins/facebook/server.py`, `sys/plugins/health/server.py`, `sys/plugins/homeassistant/server.py`, `sys/plugins/instagram/server.py`, `sys/plugins/linkcheck/server.py`, `sys/plugins/logs/server.py`, `sys/plugins/nextcloud/server.py`, `sys/plugins/notes/server.py`, `sys/plugins/patent/server.py`, `sys/plugins/projects/server.py`, `sys/plugins/pyenv/server.py`, `sys/plugins/routine_status/server.py`, `sys/plugins/routines/server.py`, `sys/plugins/runs/server.py`, `sys/plugins/security/server.py`, `sys/plugins/self/server.py`, `sys/plugins/senses/server.py`, `sys/plugins/tiktok/authorize.py`, `sys/plugins/tiktok/server.py`, `sys/plugins/userpdfs/server.py`, `sys/plugins/weather/server.py`, `sys_approvals`, `sys_autonomy`, `sys_backup`, `sys_backup_crypto`, `sys_bugreport`, `sys_capabilities`, `sys_cloud_consent`, `sys_commands`, `sys_config`, `sys_devices`, `sys_disclosure`, `sys_ethics`, `sys_features`, `sys_formats`, `sys_health`, `sys_ideas`, `sys_log`, `sys_logread`, `sys_metrics`, `sys_persona`, `sys_push`, `sys_reset`, `sys_routine_advice`, `sys_routine_templates`, `sys_routines`, `sys_seal`, `sys_soak`, `sys_social_guard`, `sys_trash`, `sys_update`, `sys_uploads`, `sys_user_config`, `sys_users`, `sys_users_layout`, `sys_users_mode` | 141 |
| `agt_calls` | `agt_loop`, `mdl_router` | 0 |
| `agt_change` | `agt_loop_make`, `api.agents` | 2 |
| `agt_forge` | `agt_forge_data`, `agt_loop`, `api.agents`, `api.forge`, `script/bench_forge.py` | 1 |
| `agt_forge_data` | `agt_forge` | 0 |
| `agt_loop` | `api.agents`, `api.routines` | 3 |
| `agt_loop_make` | `agt_loop` | 0 |
| `agt_loop_report` | `agt_loop` | 0 |
| `agt_react` | `api.agents` | 1 |
| `api` | `api.users`, `script/bench_router.py`, `script/svc_api.py` | 2 |
| `api.access` | `api (MODULES)` | 0 |
| `api.accounts` | `api (MODULES)` | 0 |
| `api.activity` | `api (MODULES)`, `api.core`, `api.rem`, `api.social`, `script/svc_api.py` | 0 |
| `api.agents` | `api (MODULES)`, `api.core`, `api.core_route`, `api.projects_plan`, `api.rem`, `api.routines`, `api.social`, `api.updates` | 0 |
| `api.autonomy` | `api (MODULES)` | 0 |
| `api.backup` | `api (MODULES)`, `api.system` | 0 |
| `api.bugreport` | `api (MODULES)` | 0 |
| `api.calendar` | `api (MODULES)`, `script/svc_api.py` | 0 |
| `api.care` | `api (MODULES)` | 0 |
| `api.core` | `api.access`, `api.accounts`, `api.activity`, `api.agents`, `api.autonomy`, `api.backup`, `api.bugreport`, `api.calendar`, `api.care`, `api.core_route`, `api.diet`, `api.dj`, `api.documents`, `api.forge`, `api.harvester`, `api.home`, `api.https`, `api.incidents`, `api.knowledge`, `api.models`, `api.models_custom`, `api.oai`, `api.oauth`, `api.places`, `api.preview`, `api.projects`, `api.projects_plan`, `api.rem`, `api.routine_advice`, `api.routines`, `api.runs`, `api.security`, `api.security_ciso`, `api.social`, `api.synapses`, `api.system`, `api.tunnel`, `api.updates`, `api.uploads`, `api.users`, `api.voice`, `script/bench_router.py`, `script/svc_api.py` | 1 |
| `api.core_route` | `api.core`, `script/bench_router.py` | 0 |
| `api.diet` | `api (MODULES)`, `script/svc_api.py` | 0 |
| `api.dj` | `api (MODULES)` | 0 |
| `api.documents` | `api (MODULES)` | 0 |
| `api.forge` | `api (MODULES)`, `api.agents` | 0 |
| `api.harvester` | `api (MODULES)` | 0 |
| `api.home` | `api (MODULES)` | 0 |
| `api.https` | `api (MODULES)` | 0 |
| `api.incidents` | `api (MODULES)` | 0 |
| `api.knowledge` | `api (MODULES)` | 0 |
| `api.models` | `api (MODULES)` | 0 |
| `api.models_custom` | `api (MODULES)` | 0 |
| `api.oai` | `api (MODULES)` | 0 |
| `api.oauth` | `api (MODULES)` | 0 |
| `api.places` | `api (MODULES)` | 0 |
| `api.preview` | `api (MODULES)` | 0 |
| `api.projects` | `api (MODULES)` | 0 |
| `api.projects_plan` | `api (MODULES)`, `api.rem` | 0 |
| `api.rem` | `api (MODULES)` | 0 |
| `api.routine_advice` | `api (MODULES)` | 0 |
| `api.routines` | `api (MODULES)`, `api.forge`, `api.routine_advice` | 0 |
| `api.runs` | `api (MODULES)` | 0 |
| `api.security` | `api (MODULES)`, `script/svc_api.py` | 0 |
| `api.security_ciso` | `api (MODULES)` | 0 |
| `api.social` | `api (MODULES)`, `api.routines` | 0 |
| `api.synapses` | `api (MODULES)` | 0 |
| `api.system` | `api (MODULES)`, `api.agents`, `api.incidents` | 0 |
| `api.tunnel` | `api (MODULES)`, `api.agents`, `api.system`, `script/svc_api.py` | 0 |
| `api.updates` | `api (MODULES)`, `api.agents`, `api.routines`, `script/svc_api.py` | 1 |
| `api.uploads` | `api (MODULES)` | 0 |
| `api.users` | `api (MODULES)`, `api.agents`, `api.autonomy`, `api.backup`, `api.calendar`, `api.diet`, `api.harvester`, `api.https`, `api.incidents`, `api.knowledge`, `api.models`, `api.models_custom`, `api.oai`, `api.rem`, `api.routines`, `api.security`, `api.security_ciso`, `api.synapses`, `api.updates` | 0 |
| `api.voice` | `api (MODULES)` | 0 |
| `aud_analysis` | `aud_deck`, `aud_dj`, `aud_synth` | 2 |
| `aud_deck` | `api.dj`, `aud_dj` | 1 |
| `aud_dj` | `api.dj`, `aud_deck`, `sys/plugins/dj/server.py` | 1 |
| `aud_synth` | `aud_deck`, `aud_dj` | 0 |
| `cal_external` | `api.calendar`, `sys/plugins/calendar/server.py` | 1 |
| `cal_store` | `api.calendar`, `cal_text`, `sys/plugins/calendar/server.py` | 1 |
| `cal_text` | `api.calendar`, `sys/plugins/calendar/server.py` | 1 |
| `doc_artifact` | `agt_loop_make`, `api.preview`, `api.projects` | 1 |
| `doc_pdf` | `api.documents`, `api.synapses`, `sys/plugins/documents/server.py`, `sys_routines`, `sys_uploads` | 2 |
| `doc_preview` | `api.preview`, `api.projects_plan`, `prj_browse` | 1 |
| `fw_drivers` | `sec_fwapi`, `sec_fwwrite` | 2 |
| `fw_drivers.sophos` | `fw_drivers (KINDS)` | 2 |
| `hlt_diet` | `api.diet`, `sys/plugins/health/server.py` | 1 |
| `hlt_diet_read` | `hlt_diet` | 0 |
| `hlt_doctor` | `api.care`, `sys/plugins/health/server.py` | 1 |
| `hlt_labs` | `api.care`, `sys/plugins/health/server.py` | 1 |
| `hlt_store` | `api.care`, `api.diet`, `hlt_diet`, `hlt_labs`, `sys/plugins/health/server.py` | 3 |
| `hom_devices` | `api.home`, `api.routines` | 1 |
| `hom_scenes` | `agt_loop`, `api.home`, `api.routines` | 1 |
| `img_edit` | `api.core_route` | 1 |
| `kno_about` | `kno_answer` | 1 |
| `kno_abstain` | `kno_answer`, `kno_study` | 1 |
| `kno_acquire` | `api.core_route`, `api.runs`, `kno_acquire_more`, `kno_sources`, `kno_study`, `script/svc_harvester.py`, `script/vault_realign.py` | 1 |
| `kno_acquire_more` | `kno_acquire` | 1 |
| `kno_answer` | `agt_loop`, `api.agents`, `api.core`, `api.core_route`, `api.forge`, `api.incidents`, `api.models_custom`, `api.routines`, `api.updates`, `kno_acquire`, `kno_followup`, `script/bench_common.py`, `script/bench_domains.py`, `script/bench_followup.py`, `script/bench_vault_diag.py` | 7 |
| `kno_arxiv` | `kno_acquire`, `kno_sources`, `script/svc_harvester.py`, `script/vault_realign.py` | 1 |
| `kno_attach` | `api.core_route`, `api.runs`, `kno_answer`, `kno_video` | 3 |
| `kno_cites` | `kno_split`, `script/bench_domains.py` | 1 |
| `kno_deduce` | `api.rem`, `api.synapses` | 1 |
| `kno_dedup` | `api.knowledge`, `kno_ingest`, `kno_vault_audit`, `script/vault_realign.py` | 2 |
| `kno_docs` | `kno_sources` | 1 |
| `kno_domain` | `kno_vault_audit`, `script/svc_harvester.py`, `script/vault_realign.py` | 1 |
| `kno_followup` | `api.core_route`, `api.runs`, `kno_answer` | 2 |
| `kno_grid` | `kno_think` | 1 |
| `kno_harvest` | `api.harvester`, `kno_harvest_plan`, `script/svc_harvester.py` | 2 |
| `kno_harvest_plan` | `script/svc_harvester.py` | 1 |
| `kno_ingest` | `api.knowledge`, `hlt_diet`, `hlt_store`, `kno_acquire`, `kno_attach`, `script/kno_import.py`, `script/svc_harvester.py` | 6 |
| `kno_lessons` | `kno_answer`, `script/bench_learn.py` | 1 |
| `kno_mood` | `api.core`, `api.rem`, `kno_morning`, `kno_rem`, `mdl_tts` | 1 |
| `kno_morning` | `api.rem` | 1 |
| `kno_read` | `kno_think`, `script/bench_router.py`, `script/bench_vault_diag.py` | 4 |
| `kno_rem` | `api.agents`, `api.rem`, `kno_morning`, `kno_review`, `kno_study` | 1 |
| `kno_review` | `api.rem` | 1 |
| `kno_self` | `kno_answer` | 1 |
| `kno_shadow` | `api.core_route`, `api.runs`, `kno_review`, `kno_train`, `script/shadow_seed.py`, `script/svc_api.py`, `sys_capabilities` | 3 |
| `kno_social` | `api.rem`, `api.social`, `kno_rem`, `kno_story_auto` | 0 |
| `kno_sources` | `api.harvester`, `kno_acquire_more`, `kno_docs`, `kno_harvest_plan`, `kno_shadow`, `script/svc_harvester.py`, `script/sys_calibrate.py`, `script/sys_domains.py`, `script/vault_realign.py` | 6 |
| `kno_split` | `kno_answer`, `kno_stages`, `script/bench_domains.py` | 1 |
| `kno_stages` | `kno_answer`, `kno_deduce`, `kno_split` | 2 |
| `kno_story` | `api.social`, `kno_story_auto`, `script/story_intro_make.py`, `script/story_music_fetch.py` | 2 |
| `kno_story_auto` | `api.routines` | 1 |
| `kno_study` | `api.rem`, `kno_deduce`, `kno_morning`, `kno_review`, `kno_train` | 1 |
| `kno_synapse` | `api.knowledge`, `api.synapses`, `kno_deduce`, `kno_morning`, `kno_synapse2`, `kno_trail`, `sol_search`, `sys_capabilities` | 1 |
| `kno_synapse2` | `api.synapses` | 1 |
| `kno_think` | `api.runs`, `kno_answer` | 1 |
| `kno_trail` | `kno_answer`, `kno_stages` | 1 |
| `kno_train` | `api.rem`, `kno_deduce` | 1 |
| `kno_vault_audit` | `api.rem` | 1 |
| `kno_video` | `kno_attach` | 1 |
| `kno_web` | `kno_read` | 1 |
| `mdl_accounts` | `api.accounts`, `mdl_cloud`, `mdl_router`, `mdl_services` | 2 |
| `mdl_budget` | `api.models`, `mdl_cloud`, `mdl_media`, `mdl_router`, `sys_health` | 3 |
| `mdl_cloud` | `mdl_router`, `script/bench_agi.py`, `script/bench_domain_assign.py`, `script/bench_forge.py`, `script/bench_honesty.py`, `script/bench_memory_days.py`, `script/bench_public.py`, `script/bench_quality.py`, `script/bench_router.py` | 2 |
| `mdl_custom` | `api.models_custom`, `script/sys_model_check.py` | 1 |
| `mdl_embedder` | `script/bench_retrieval.py`, `script/svc_models.py`, `script/sys_calibrate.py` | 1 |
| `mdl_formats` | `mdl_custom`, `mdl_llm`, `mdl_router`, `script/svc_llm.py`, `script/sys_model_check.py` | 2 |
| `mdl_gguf` | `mdl_custom`, `mdl_formats`, `script/sys_model_check.py` | 2 |
| `mdl_image` | `agt_loop_make`, `api.core_route`, `kno_rem`, `kno_story`, `mdl_tts`, `mdl_video` | 3 |
| `mdl_llm` | `agt_loop_report`, `kno_answer`, `mdl_cloud`, `mdl_custom`, `mdl_router`, `script/bench_domain_assign.py`, `script/bench_forge.py`, `script/bench_learn.py`, `script/bench_public.py`, `script/svc_harvester.py`, `script/vault_realign.py`, `sys/plugins/homeassistant/server.py`, `sys/plugins/senses/server.py` | 8 |
| `mdl_media` | `api.core_route`, `api.models`, `mdl_image`, `mdl_modes`, `mdl_tts`, `mdl_video`, `sns_av`, `sys_features` | 3 |
| `mdl_modes` | `api.models`, `mdl_custom` | 2 |
| `mdl_remote` | `api.core`, `script/bench_common.py`, `script/bench_domain_assign.py`, `script/bench_domains.py`, `script/bench_followup.py`, `script/bench_learn.py`, `script/bench_retrieval.py`, `script/bench_vault_diag.py` | 1 |
| `mdl_reranker` | `script/bench_retrieval.py`, `script/svc_models.py`, `script/sys_calibrate.py` | 2 |
| `mdl_router` | `agt_loop`, `api.accounts`, `api.care`, `api.diet`, `api.forge`, `api.models`, `api.runs`, `api.system`, `kno_answer`, `kno_grid`, `kno_read`, `kno_stages`, `mdl_accounts`, `mdl_llm`, `mdl_media`, `mdl_modes`, `mdl_services`, `script/bench_domain_assign.py`, `script/bench_forge.py`, `script/bench_honeypot.py`, `script/bench_learn.py`, `script/bench_preflight.py`, `script/bench_public.py`, `script/bench_router.py`, `script/svc_harvester.py`, `script/sys_cloud_setup.py`, `script/sys_doctor.py`, `script/vault_realign.py`, `sec_fwplan`, `sec_outbound`, `sys/plugins/cloud/server.py`, `sys_capabilities`, `sys_features`, `sys_health`, `sys_metrics` | 13 |
| `mdl_services` | `api.accounts`, `mdl_router` | 1 |
| `mdl_stt` | `script/svc_models.py` | 1 |
| `mdl_tts` | `api.core`, `api.voice`, `kno_story`, `mdl_image`, `sys_capabilities` | 3 |
| `mdl_video` | `api.core_route`, `api.runs`, `script/story_intro_make.py` | 1 |
| `net_cfwaf` | `api.security`, `sys/plugins/cloudflare/server.py` | 1 |
| `net_cloudflare` | `api.system`, `api.tunnel`, `net_cfwaf`, `sys/plugins/cloudflare/server.py` | 2 |
| `net_geo` | `api.security`, `net_trace` | 1 |
| `net_https` | `api.agents`, `api.https`, `api.system`, `script/sys_install_services.py`, `script/sys_ready.py` | 2 |
| `net_trace` | `api.incidents`, `api.security` | 1 |
| `plg_access` | `api.agents`, `api.core` | 1 |
| `plg_deps` | `api.agents` | 1 |
| `plg_host` | `agt_forge`, `agt_loop`, `api.agents`, `api.core`, `kno_rem`, `kno_social`, `plg_access`, `script/bench_forge.py` | 5 |
| `plg_sandbox` | `plg_host` | 3 |
| `plg_shadow` | `agt_loop` | 1 |
| `plg_trash` | `api.agents` | 1 |
| `prj_browse` | `api.projects`, `api.projects_plan` | 0 |
| `prj_docs` | `api.projects_plan` | 1 |
| `prj_plan` | `api.projects_plan` | 1 |
| `prj_reports` | `agt_loop`, `api.projects` | 1 |
| `prj_run` | `agt_loop`, `api.projects_plan`, `kno_grid`, `prj_term` | 1 |
| `prj_term` | `api.projects` | 1 |
| `sec_audit` | `api.security_ciso`, `sys/plugins/security/server.py` | 2 |
| `sec_baseline` | `script/svc_rem.py`, `script/svc_sentinel.py` | 1 |
| `sec_defence` | `api.incidents`, `api.security`, `kno_morning`, `net_cfwaf`, `sec_hostfw`, `sys_autonomy` | 3 |
| `sec_detonate` | `agt_loop`, `api.knowledge`, `kno_ingest`, `kno_read`, `script/bench_honeypot.py`, `sec_linkcheck`, `sys/plugins/linkcheck/server.py` | 2 |
| `sec_fwapi` | `api.core`, `api.incidents`, `api.security`, `api.security_ciso`, `fw_drivers.sophos`, `sec_audit`, `sec_defence`, `sec_fwconf`, `sec_fwplan`, `sec_fwport`, `sec_fwwrite`, `sec_hostfw`, `sec_netmap`, `sec_report`, `sys/plugins/security/server.py`, `sys_capabilities` | 5 |
| `sec_fwconf` | `sec_audit`, `sec_fwplan`, `sec_fwport`, `sec_fwwrite`, `sys/plugins/security/server.py` | 1 |
| `sec_fwdocs` | `api.security_ciso`, `sec_fwplan`, `sys/plugins/security/server.py` | 1 |
| `sec_fwplan` | `api.security_ciso`, `sys/plugins/security/server.py` | 3 |
| `sec_fwport` | `api.security`, `api.security_ciso`, `sys/plugins/security/server.py` | 1 |
| `sec_fwwrite` | `api.security_ciso`, `sec_fwplan`, `sec_fwport`, `sys/plugins/security/server.py` | 5 |
| `sec_hostaudit` | `api.security_ciso` | 1 |
| `sec_hostfw` | `api.core`, `api.incidents`, `api.security`, `api.security_ciso`, `sec_report` | 1 |
| `sec_hunt` | `api.security_ciso`, `sys/plugins/security/server.py` | 1 |
| `sec_incidents` | `api.incidents`, `api.security`, `api.security_ciso`, `kno_mood`, `sec_report`, `sec_scorecard`, `sys_autonomy` | 5 |
| `sec_intel` | `api.incidents`, `api.security`, `net_cfwaf`, `script/svc_rem.py`, `sec_defence`, `sec_fwport`, `sec_hunt`, `sec_report`, `sec_shared` | 5 |
| `sec_linkcheck` | `agt_loop`, `kno_web`, `sec_detonate`, `sys/plugins/linkcheck/server.py` | 2 |
| `sec_mask` | `agt_forge`, `kno_web`, `mdl_media`, `mdl_router`, `script/dev_privacy_scan.py`, `script/shadow_seed.py`, `sec_privacy`, `sys_bugreport` | 2 |
| `sec_netmap` | `api.incidents`, `api.security`, `api.security_ciso`, `sec_hunt`, `sys/plugins/security/server.py`, `sys_capabilities` | 2 |
| `sec_outbound` | `api.security` | 0 |
| `sec_playbook` | `api.security_ciso`, `sys/plugins/security/server.py` | 1 |
| `sec_privacy` | `agt_loop`, `api.social`, `kno_story_auto`, `sys_bugreport` | 1 |
| `sec_profile` | `api.security`, `sec_hunt` | 1 |
| `sec_report` | `api.security`, `sys/plugins/security/server.py` | 1 |
| `sec_rules` | `api.security`, `script/svc_sentinel.py`, `sec_profile` | 1 |
| `sec_scorecard` | `api.incidents` | 1 |
| `sec_sentinel` | `api.incidents`, `script/svc_sentinel.py`, `sec_hunt`, `sec_playbook`, `sec_profile`, `sys/plugins/security/server.py` | 3 |
| `sec_shared` | `api.incidents` | 1 |
| `sns_av` | `api.knowledge`, `kno_video`, `mdl_stt`, `sys/plugins/senses/server.py` | 2 |
| `sns_clock` | `agt_loop`, `kno_followup`, `kno_rem`, `kno_review`, `kno_self`, `kno_stages`, `script/bench_followup.py`, `script/svc_rem.py`, `sys_routines` | 1 |
| `sns_weather` | `kno_rem`, `kno_self` | 0 |
| `sol_index` | `kno_answer`, `kno_harvest_plan`, `kno_ingest`, `script/bench_retrieval.py`, `sol_search`, `sol_writer` | 9 |
| `sol_lexical` | `sol_index`, `sol_search` | 1 |
| `sol_reader` | `api.core`, `api.core_route`, `api.system`, `kno_answer`, `kno_ingest`, `script/bench_quality.py`, `script/shadow_seed.py`, `sol_index`, `sol_search`, `sol_writer` | 12 |
| `sol_schema` | `api.agents`, `api.core_route`, `api.harvester`, `api.knowledge`, `api.runs`, `kno_acquire`, `kno_answer`, `kno_attach`, `kno_domain`, `kno_followup`, `kno_ingest`, `kno_rem`, `kno_self`, `script/bench_domain_assign.py`, `script/bench_followup.py`, `script/bench_retrieval.py`, `script/kno_migrate_legacy.py`, `script/svc_harvester.py`, `sol_reader`, `sol_search`, `sol_vault`, `sol_writer` | 16 |
| `sol_search` | `kno_answer`, `kno_cites`, `kno_followup`, `kno_stages`, `script/bench_retrieval.py` | 6 |
| `sol_vault` | `kno_harvest_plan`, `kno_rem`, `kno_vault_audit`, `script/bench_domain_assign.py`, `script/bench_vault_diag.py`, `script/svc_api.py`, `script/vault_realign.py`, `sol_index`, `sol_reader`, `sol_writer` | 3 |
| `sol_writer` | `kno_answer`, `kno_ingest`, `script/bench_retrieval.py` | 15 |
| `sys_approvals` | `agt_loop`, `agt_loop_make`, `api.agents`, `api.autonomy`, `api.forge`, `api.routines`, `api.security`, `api.social`, `api.updates`, `kno_story_auto`, `sys_social_guard` | 7 |
| `sys_autonomy` | `agt_loop`, `api.autonomy`, `api.core_route`, `api.forge`, `api.updates`, `hom_devices`, `net_cfwaf`, `sec_defence`, `sec_outbound` | 2 |
| `sys_backup` | `api.backup`, `script/svc_backup.py`, `script/sys_doctor.py`, `script/sys_nas_mount.py`, `script/sys_restore.py`, `script/sys_users_migrate.py`, `sec_report`, `sys_backup_crypto`, `sys_capabilities`, `sys_health` | 2 |
| `sys_backup_crypto` | `sys_backup` | 0 |
| `sys_bugreport` | `api.bugreport` | 1 |
| `sys_capabilities` | `api.knowledge` | 1 |
| `sys_cloud_consent` | `mdl_modes`, `mdl_router`, `script/sys_ethics_sign.py` | 1 |
| `sys_commands` | `api.updates`, `sys_update` | 1 |
| `sys_config` | `agt_change`, `agt_forge`, `agt_forge_data`, `agt_loop`, `agt_react`, `api.autonomy`, `api.core`, `api.harvester`, `api.oauth`, `api.system`, `api.tunnel`, `api.updates`, `cal_store`, `doc_artifact`, `doc_pdf`, `doc_preview`, `hlt_diet`, `hlt_doctor`, `hlt_labs`, `hlt_store`, `hom_devices`, `kno_acquire`, `kno_answer`, `kno_attach`, `kno_deduce`, `kno_dedup`, `kno_docs`, `kno_harvest`, `kno_harvest_plan`, `kno_ingest`, `kno_lessons`, `kno_mood`, `kno_morning`, `kno_rem`, `kno_review`, `kno_shadow`, `kno_social`, `kno_sources`, `kno_story`, `kno_story_auto`, `kno_study`, `kno_synapse`, `kno_synapse2`, `kno_trail`, `kno_train`, `kno_vault_audit`, `kno_video`, `mdl_accounts`, `mdl_budget`, `mdl_cloud`, `mdl_custom`, `mdl_embedder`, `mdl_formats`, `mdl_image`, `mdl_llm`, `mdl_media`, `mdl_modes`, `mdl_remote`, `mdl_reranker`, `mdl_router`, `mdl_services`, `mdl_stt`, `mdl_tts`, `mdl_video`, `net_cfwaf`, `net_cloudflare`, `net_geo`, `net_https`, `net_trace`, `plg_access`, `plg_host`, `plg_sandbox`, `plg_shadow`, `plg_trash`, `prj_browse`, `prj_docs`, `prj_plan`, `prj_reports`, `prj_run`, `prj_term`, `script/bench_common.py`, `script/bench_domain_assign.py`, `script/bench_domains.py`, `script/bench_followup.py`, `script/bench_forge.py`, `script/bench_honeypot.py`, `script/bench_image.py`, `script/bench_learn.py`, `script/bench_preflight.py`, `script/bench_quality.py`, `script/bench_repair.py`, `script/bench_retrieval.py`, `script/bench_router.py`, `script/bench_vault_diag.py`, `script/dev_privacy_scan.py`, `script/img_ai.py`, `script/img_paint.py`, `script/kno_import.py`, `script/kno_migrate_legacy.py`, `script/shadow_seed.py`, `script/story_intro_make.py`, `script/story_music_fetch.py`, `script/svc_backup.py`, `script/svc_harvester.py`, `script/svc_llm.py`, `script/svc_models.py`, `script/svc_rem.py`, `script/svc_sentinel.py`, `script/sys_backup_retime.py`, `script/sys_calibrate.py`, `script/sys_cloud_setup.py`, `script/sys_commands_write.py`, `script/sys_doctor.py`, `script/sys_domains.py`, `script/sys_env_sync.py`, `script/sys_ethics_sign.py`, `script/sys_factory_reset.py`, `script/sys_install_services.py`, `script/sys_nas_mount.py`, `script/sys_ready.py`, `script/sys_restore.py`, `script/sys_users_migrate.py`, `script/vault_realign.py`, `script/vid_ai.py`, `sec_audit`, `sec_baseline`, `sec_defence`, `sec_detonate`, `sec_fwapi`, `sec_fwconf`, `sec_fwdocs`, `sec_fwplan`, `sec_fwport`, `sec_fwwrite`, `sec_hostaudit`, `sec_hostfw`, `sec_hunt`, `sec_incidents`, `sec_intel`, `sec_linkcheck`, `sec_mask`, `sec_netmap`, `sec_outbound`, `sec_privacy`, `sec_profile`, `sec_report`, `sec_rules`, `sec_scorecard`, `sec_shared`, `sns_av`, `sns_clock`, `sns_weather`, `sol_index`, `sol_lexical`, `sol_reader`, `sol_search`, `sol_vault`, `sol_writer`, `sys/plugins/backup/server.py`, `sys/plugins/cad/server.py`, `sys/plugins/calendar/server.py`, `sys/plugins/cloud/server.py`, `sys/plugins/cloudflare/server.py`, `sys/plugins/diary/server.py`, `sys/plugins/dj/server.py`, `sys/plugins/documents/server.py`, `sys/plugins/dropbox/authorize.py`, `sys/plugins/dropbox/server.py`, `sys/plugins/email_diag/server.py`, `sys/plugins/expenses/server.py`, `sys/plugins/facebook/server.py`, `sys/plugins/health/server.py`, `sys/plugins/homeassistant/server.py`, `sys/plugins/instagram/server.py`, `sys/plugins/linkcheck/server.py`, `sys/plugins/logs/server.py`, `sys/plugins/nextcloud/server.py`, `sys/plugins/notes/server.py`, `sys/plugins/patent/server.py`, `sys/plugins/projects/server.py`, `sys/plugins/pyenv/server.py`, `sys/plugins/routine_status/server.py`, `sys/plugins/routines/server.py`, `sys/plugins/runs/server.py`, `sys/plugins/security/server.py`, `sys/plugins/self/server.py`, `sys/plugins/senses/server.py`, `sys/plugins/tiktok/authorize.py`, `sys/plugins/tiktok/server.py`, `sys/plugins/userpdfs/server.py`, `sys/plugins/weather/server.py`, `sys_approvals`, `sys_autonomy`, `sys_backup`, `sys_backup_crypto`, `sys_bugreport`, `sys_capabilities`, `sys_cloud_consent`, `sys_commands`, `sys_devices`, `sys_disclosure`, `sys_ethics`, `sys_features`, `sys_formats`, `sys_health`, `sys_ideas`, `sys_log`, `sys_logread`, `sys_persona`, `sys_push`, `sys_reset`, `sys_routine_advice`, `sys_routine_templates`, `sys_routines`, `sys_seal`, `sys_soak`, `sys_social_guard`, `sys_trash`, `sys_update`, `sys_uploads`, `sys_user_config`, `sys_users`, `sys_users_layout`, `sys_users_mode` | 32 |
| `sys_context` | `api.activity`, `api.calendar`, `api.care`, `api.core`, `api.core_route`, `api.diet`, `api.dj`, `api.rem`, `api.routine_advice`, `api.routines`, `api.tunnel`, `api.users`, `hom_scenes`, `sys_config`, `sys_log` | 2 |
| `sys_devices` | `api.access`, `api.core`, `api.users`, `sys_users_layout` | 2 |
| `sys_disclosure` | `agt_loop`, `api.core_route`, `api.social`, `doc_pdf`, `kno_social`, `kno_story`, `mdl_image`, `mdl_video`, `sys/plugins/projects/server.py` | 1 |
| `sys_ethics` | `agt_change`, `agt_forge`, `agt_loop`, `agt_loop_make`, `api.agents`, `api.autonomy`, `api.models`, `mdl_cloud`, `mdl_media`, `mdl_modes`, `mdl_router`, `net_cfwaf`, `plg_host`, `script/bench_preflight.py`, `script/dev_license_headers.py`, `script/svc_api.py`, `script/svc_harvester.py`, `script/svc_llm.py`, `script/svc_models.py`, `script/svc_rem.py`, `script/svc_sentinel.py`, `script/sys_ethics_sign.py`, `sec_defence`, `sys_approvals`, `sys_cloud_consent`, `sys_commands`, `sys_disclosure`, `sys_features`, `sys_health`, `sys_update` | 10 |
| `sys_features` | `agt_loop_make`, `api.bugreport`, `api.core`, `api.core_route`, `api.knowledge`, `kno_attach`, `kno_rem`, `kno_video`, `mdl_modes`, `script/sys_doctor.py`, `sys_health` | 4 |
| `sys_formats` | `script/sys_restore.py`, `sys_backup` | 1 |
| `sys_health` | `api.activity`, `api.bugreport`, `api.core`, `api.core_route`, `mdl_custom`, `mdl_modes`, `script/svc_harvester.py`, `script/svc_rem.py`, `script/svc_sentinel.py` | 4 |
| `sys_ideas` | `api.bugreport`, `sys_bugreport` | 2 |
| `sys_log` | `agt_change`, `agt_forge`, `agt_loop`, `api.access`, `api.activity`, `api.autonomy`, `api.core`, `api.security`, `api.system`, `api.users`, `doc_pdf`, `kno_acquire`, `kno_answer`, `kno_attach`, `kno_harvest_plan`, `kno_ingest`, `kno_lessons`, `kno_read`, `kno_rem`, `kno_social`, `kno_story`, `kno_story_auto`, `kno_vault_audit`, `kno_video`, `mdl_budget`, `mdl_cloud`, `mdl_embedder`, `mdl_image`, `mdl_llm`, `mdl_media`, `mdl_reranker`, `mdl_router`, `mdl_stt`, `mdl_tts`, `mdl_video`, `net_cfwaf`, `net_https`, `plg_host`, `plg_trash`, `script/bench_retrieval.py`, `script/kno_migrate_legacy.py`, `script/svc_backup.py`, `script/svc_harvester.py`, `script/svc_llm.py`, `script/svc_models.py`, `script/svc_rem.py`, `script/svc_sentinel.py`, `script/sys_cloud_setup.py`, `sec_defence`, `sec_detonate`, `sec_fwdocs`, `sec_fwport`, `sec_fwwrite`, `sec_incidents`, `sec_linkcheck`, `sns_av`, `sns_weather`, `sol_index`, `sol_lexical`, `sol_search`, `sol_writer`, `sys_approvals`, `sys_backup`, `sys_push`, `sys_update` | 6 |
| `sys_logread` | `agt_react`, `api.activity`, `api.agents`, `kno_mood`, `kno_rem`, `kno_self`, `sys/plugins/self/server.py`, `sys_bugreport` | 1 |
| `sys_metrics` | `api.routines`, `sys_health` | 1 |
| `sys_persona` | `api.users`, `kno_morning`, `kno_rem`, `kno_self`, `kno_social` | 1 |
| `sys_push` | `api.core`, `api.routines`, `sec_outbound`, `sys_capabilities` | 5 |
| `sys_replay` | `script/svc_api.py` | 1 |
| `sys_reset` | `api.system`, `script/sys_factory_reset.py` | 1 |
| `sys_routine_advice` | `api.home`, `api.routine_advice`, `hom_devices` | 2 |
| `sys_routine_templates` | `api.routine_advice` | 1 |
| `sys_routines` | `api.forge`, `api.home`, `api.routine_advice`, `api.routines`, `hom_devices`, `hom_scenes`, `sys_routine_advice`, `sys_routine_templates` | 5 |
| `sys_runs` | `api.core` | 1 |
| `sys_seal` | `api.care`, `api.diet`, `cal_store`, `hlt_diet`, `hlt_doctor`, `hlt_labs`, `hlt_store`, `sec_netmap` | 2 |
| `sys_soak` | `api.activity`, `script/svc_rem.py` | 1 |
| `sys_social_guard` | `agt_loop`, `api.social`, `kno_story_auto` | 1 |
| `sys_tests` | `agt_change`, `agt_loop_make`, `script/bench_repair.py`, `sys/plugins/self/server.py`, `sys_update` | 0 |
| `sys_trash` | `api.dj`, `api.documents`, `api.uploads`, `sys_uploads` | 1 |
| `sys_update` | `api.agents`, `api.routines`, `api.updates`, `sys_commands` | 2 |
| `sys_uploads` | `agt_loop_make`, `api.agents`, `api.core_route`, `api.knowledge`, `api.runs`, `api.social`, `api.uploads`, `doc_artifact`, `doc_preview`, `kno_review`, `kno_study`, `sys_routines` | 5 |
| `sys_user_config` | `api.autonomy`, `api.core`, `api.oauth`, `api.system`, `api.users`, `script/svc_api.py`, `sec_privacy`, `sys_config`, `sys_users_layout` | 4 |
| `sys_users` | `api.autonomy`, `api.core`, `api.users`, `mdl_accounts`, `script/sys_users_migrate.py`, `sec_privacy`, `sys_users_layout`, `sys_users_mode` | 6 |
| `sys_users_layout` | `agt_forge`, `agt_forge_data`, `agt_react`, `api.autonomy`, `api.oauth`, `api.system`, `api.users`, `cal_store`, `kno_mood`, `kno_review`, `kno_shadow`, `kno_story`, `kno_study`, `mdl_tts`, `plg_sandbox`, `plg_shadow`, `prj_docs`, `prj_plan`, `prj_reports`, `script/bench_forge.py`, `script/svc_api.py`, `script/sys_users_migrate.py`, `sec_privacy`, `sol_index`, `sol_vault`, `sys/plugins/diary/server.py`, `sys/plugins/runs/server.py`, `sys_approvals`, `sys_config`, `sys_ideas`, `sys_push`, `sys_routines`, `sys_seal`, `sys_trash`, `sys_user_config`, `sys_users_mode` | 6 |
| `sys_users_mode` | `api.system` | 1 |
| `txt_compress` | `kno_read`, `kno_stages` | 1 |
| `txt_ical` | `cal_external`, `cal_store`, `cal_text`, `sys/plugins/calendar/server.py` | 1 |
| `txt_lang` | `agt_loop`, `api.documents`, `api.social`, `kno_acquire`, `kno_answer`, `kno_attach`, `kno_grid`, `kno_ingest`, `kno_read`, `kno_rem`, `kno_self`, `kno_social`, `kno_stages`, `kno_story_auto`, `script/bench_quality.py`, `script/kno_migrate_legacy.py`, `sys/plugins/documents/server.py` | 1 |

## WebUI modules: who imports them

| module | imported by |
|---|---|
| `js/api.js` | `js/artifact.js`, `js/backup.js`, `js/calendar_alerts.js`, `js/cards.js`, `js/diet.js`, `js/main.js`, `js/modules/accounts.js`, `js/modules/accounts_services.js`, `js/modules/alerts.js`, `js/modules/approvals.js`, `js/modules/aurorafw.js`, `js/modules/autonomy.js`, `js/modules/autonomy_box.js`, `js/modules/brain.js`, `js/modules/bugreport.js`, `js/modules/calendar.js`, `js/modules/calendar_form.js`, `js/modules/care.js`, `js/modules/care_diet.js`, `js/modules/care_doctor.js`, `js/modules/care_values.js`, `js/modules/chat.js`, `js/modules/chat_media.js`, `js/modules/ciso.js`, `js/modules/deductions_box.js`, `js/modules/diary.js`, `js/modules/dj.js`, `js/modules/dreams.js`, `js/modules/firewall.js`, `js/modules/harvest_plan.js`, `js/modules/harvester.js`, `js/modules/home.js`, `js/modules/home_scenes.js`, `js/modules/https.js`, `js/modules/ideas.js`, `js/modules/import.js`, `js/modules/memory.js`, `js/modules/metrics.js`, `js/modules/models.js`, `js/modules/models_choice.js`, `js/modules/models_custom.js`, `js/modules/models_mode.js`, `js/modules/notifications.js`, `js/modules/plugins.js`, `js/modules/project_docs.js`, `js/modules/project_plan.js`, `js/modules/project_term.js`, `js/modules/projects.js`, `js/modules/reports.js`, `js/modules/routines.js`, `js/modules/routines_templates.js`, `js/modules/runs.js`, `js/modules/security.js`, `js/modules/security_defence.js`, `js/modules/security_map.js`, `js/modules/security_watch.js`, `js/modules/settings.js`, `js/modules/social.js`, `js/modules/social_video.js`, `js/modules/status.js`, `js/modules/synapses.js`, `js/modules/today.js`, `js/modules/trace.js`, `js/modules/updates.js`, `js/modules/uploads.js`, `js/modules/users.js`, `js/push.js`, `js/restart.js`, `js/style.js`, `js/theme.js`, `js/viewer.js`, `js/welcome.js` |
| `js/artifact.js` | `js/modules/trace.js` |
| `js/backup.js` | `js/modules/plugins.js`, `js/modules/status.js` |
| `js/bus.js` | `js/main.js`, `js/modules/advanced.js`, `js/modules/alerts.js`, `js/modules/autonomy_box.js`, `js/modules/chat.js`, `js/modules/ciso.js`, `js/modules/notifications.js`, `js/modules/plugins.js`, `js/modules/projects.js`, `js/modules/security.js`, `js/modules/security_defence.js`, `js/modules/security_trace.js`, `js/modules/sky.js`, `js/modules/social.js`, `js/modules/today.js`, `js/modules/trace.js`, `js/modules/users.js`, `js/share.js`, `js/welcome.js` |
| `js/calendar_alerts.js` | `js/modules/chat.js` |
| `js/cards.js` | `js/modules/updates.js` |
| `js/diet.js` | `js/modules/care_diet.js`, `js/modules/chat.js` |
| `js/dom.js` | `js/artifact.js`, `js/backup.js`, `js/calendar_alerts.js`, `js/cards.js`, `js/diet.js`, `js/main.js`, `js/md.js`, `js/modules/accounts.js`, `js/modules/accounts_services.js`, `js/modules/advanced.js`, `js/modules/alerts.js`, `js/modules/approvals.js`, `js/modules/aurorafw.js`, `js/modules/autonomy.js`, `js/modules/autonomy_box.js`, `js/modules/brain.js`, `js/modules/bugreport.js`, `js/modules/calendar.js`, `js/modules/calendar_form.js`, `js/modules/calendar_grid.js`, `js/modules/care.js`, `js/modules/care_diet.js`, `js/modules/care_doctor.js`, `js/modules/care_values.js`, `js/modules/chat.js`, `js/modules/chat_actions.js`, `js/modules/chat_media.js`, `js/modules/chat_menu.js`, `js/modules/ciso.js`, `js/modules/deductions_box.js`, `js/modules/diary.js`, `js/modules/dj.js`, `js/modules/dj_deck.js`, `js/modules/dreams.js`, `js/modules/firewall.js`, `js/modules/guide.js`, `js/modules/harvest_plan.js`, `js/modules/harvester.js`, `js/modules/home.js`, `js/modules/home_scenes.js`, `js/modules/https.js`, `js/modules/ideas.js`, `js/modules/import.js`, `js/modules/memory.js`, `js/modules/metrics.js`, `js/modules/models.js`, `js/modules/models_choice.js`, `js/modules/models_custom.js`, `js/modules/models_mode.js`, `js/modules/notifications.js`, `js/modules/plugins.js`, `js/modules/project_docs.js`, `js/modules/project_plan.js`, `js/modules/project_term.js`, `js/modules/projects.js`, `js/modules/reports.js`, `js/modules/routines.js`, `js/modules/routines_templates.js`, `js/modules/runs.js`, `js/modules/security.js`, `js/modules/security_defence.js`, `js/modules/security_map.js`, `js/modules/security_trace.js`, `js/modules/security_watch.js`, `js/modules/settings.js`, `js/modules/social.js`, `js/modules/social_video.js`, `js/modules/status.js`, `js/modules/synapses.js`, `js/modules/today.js`, `js/modules/trace.js`, `js/modules/updates.js`, `js/modules/uploads.js`, `js/modules/users.js`, `js/mood.js`, `js/restart.js`, `js/share.js`, `js/theme.js`, `js/viewer.js`, `js/welcome.js` |
| `js/i18n.js` | `js/artifact.js`, `js/backup.js`, `js/calendar_alerts.js`, `js/cards.js`, `js/diet.js`, `js/main.js`, `js/modules/accounts.js`, `js/modules/accounts_services.js`, `js/modules/advanced.js`, `js/modules/alerts.js`, `js/modules/approvals.js`, `js/modules/aurorafw.js`, `js/modules/autonomy.js`, `js/modules/autonomy_box.js`, `js/modules/brain.js`, `js/modules/bugreport.js`, `js/modules/calendar.js`, `js/modules/calendar_form.js`, `js/modules/calendar_grid.js`, `js/modules/care.js`, `js/modules/care_diet.js`, `js/modules/care_doctor.js`, `js/modules/care_values.js`, `js/modules/chat.js`, `js/modules/chat_actions.js`, `js/modules/chat_media.js`, `js/modules/chat_menu.js`, `js/modules/ciso.js`, `js/modules/deductions_box.js`, `js/modules/diary.js`, `js/modules/dj.js`, `js/modules/dj_deck.js`, `js/modules/dreams.js`, `js/modules/firewall.js`, `js/modules/guide.js`, `js/modules/harvest_plan.js`, `js/modules/harvester.js`, `js/modules/home.js`, `js/modules/home_scenes.js`, `js/modules/https.js`, `js/modules/ideas.js`, `js/modules/ideas_page.js`, `js/modules/import.js`, `js/modules/memory.js`, `js/modules/models.js`, `js/modules/models_choice.js`, `js/modules/models_custom.js`, `js/modules/models_mode.js`, `js/modules/notifications.js`, `js/modules/plugins.js`, `js/modules/project_docs.js`, `js/modules/project_plan.js`, `js/modules/project_term.js`, `js/modules/projects.js`, `js/modules/reports.js`, `js/modules/routines.js`, `js/modules/routines_templates.js`, `js/modules/runs.js`, `js/modules/security.js`, `js/modules/security_defence.js`, `js/modules/security_map.js`, `js/modules/security_trace.js`, `js/modules/security_watch.js`, `js/modules/settings.js`, `js/modules/social.js`, `js/modules/social_video.js`, `js/modules/status.js`, `js/modules/synapses.js`, `js/modules/today.js`, `js/modules/trace.js`, `js/modules/updates.js`, `js/modules/uploads.js`, `js/modules/users.js`, `js/mood.js`, `js/restart.js`, `js/share.js`, `js/theme.js`, `js/viewer.js`, `js/welcome.js` |
| `js/main.js` | `index.html` |
| `js/md.js` | `js/modules/care.js`, `js/modules/diary.js`, `js/modules/dreams.js`, `js/modules/guide.js`, `js/modules/memory.js`, `js/modules/plugins.js`, `js/modules/projects.js`, `js/modules/reports.js`, `js/modules/routines.js`, `js/modules/security.js`, `js/modules/trace.js` |
| `js/modules.js` | `js/main.js` |
| `js/modules/accounts.js` | `js/modules.js` |
| `js/modules/accounts_services.js` | `js/modules/accounts.js` |
| `js/modules/advanced.js` | `js/modules.js` |
| `js/modules/alerts.js` | `js/modules.js` |
| `js/modules/approvals.js` | `js/modules.js`, `js/modules/social.js` |
| `js/modules/aurorafw.js` | `js/modules.js` |
| `js/modules/autonomy.js` | `js/modules.js` |
| `js/modules/autonomy_box.js` | `js/modules/approvals.js`, `js/modules/aurorafw.js`, `js/modules/ciso.js`, `js/modules/diary.js`, `js/modules/firewall.js`, `js/modules/harvester.js`, `js/modules/home.js`, `js/modules/import.js`, `js/modules/plugins.js`, `js/modules/security.js`, `js/modules/social.js`, `js/modules/synapses.js`, `js/modules/updates.js` |
| `js/modules/brain.js` | `js/modules.js` |
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
| `js/modules/chat_actions.js` | `js/modules/chat.js` |
| `js/modules/chat_media.js` | `js/modules/chat.js` |
| `js/modules/chat_menu.js` | `js/modules/chat.js` |
| `js/modules/chat_think.js` | `js/modules/chat.js`, `js/modules/chat_menu.js` |
| `js/modules/ciso.js` | `js/modules.js` |
| `js/modules/deductions_box.js` | `js/modules/synapses.js` |
| `js/modules/diary.js` | `js/modules.js` |
| `js/modules/dj.js` | `js/modules.js` |
| `js/modules/dj_deck.js` | `js/modules/dj.js` |
| `js/modules/dreams.js` | `js/modules.js` |
| `js/modules/firewall.js` | `js/modules.js` |
| `js/modules/guide.js` | `js/modules.js` |
| `js/modules/harvest_plan.js` | `js/modules/harvester.js` |
| `js/modules/harvester.js` | `js/modules.js` |
| `js/modules/home.js` | `js/modules.js` |
| `js/modules/home_scenes.js` | `js/modules/home.js` |
| `js/modules/https.js` | `js/modules.js` |
| `js/modules/ideas.js` | `js/modules/ideas_page.js` |
| `js/modules/ideas_page.js` | `js/modules.js` |
| `js/modules/import.js` | `js/modules.js` |
| `js/modules/memory.js` | `js/modules.js` |
| `js/modules/metrics.js` | `js/modules.js` |
| `js/modules/models.js` | `js/modules.js` |
| `js/modules/models_choice.js` | `js/modules/models.js`, `js/welcome.js` |
| `js/modules/models_custom.js` | `js/modules/models.js` |
| `js/modules/models_mode.js` | `js/modules/models.js`, `js/modules/models_choice.js` |
| `js/modules/models_presets.js` | `js/modules/models_choice.js`, `js/welcome.js` |
| `js/modules/notifications.js` | `js/modules.js` |
| `js/modules/plugins.js` | `js/modules.js` |
| `js/modules/project_docs.js` | `js/modules/projects.js` |
| `js/modules/project_plan.js` | `js/modules/projects.js` |
| `js/modules/project_term.js` | `js/modules/projects.js` |
| `js/modules/projects.js` | `js/modules.js` |
| `js/modules/reports.js` | `js/modules.js` |
| `js/modules/routines.js` | `js/modules.js` |
| `js/modules/routines_templates.js` | `js/modules/routines.js` |
| `js/modules/runs.js` | `js/modules.js` |
| `js/modules/security.js` | `js/modules.js`, `js/modules/security_defence_page.js`, `js/modules/security_out_page.js`, `js/modules/security_watch_page.js` |
| `js/modules/security_defence.js` | `js/modules/security.js` |
| `js/modules/security_defence_page.js` | `js/modules.js` |
| `js/modules/security_map.js` | `js/modules/security_defence.js` |
| `js/modules/security_out_page.js` | `js/modules.js` |
| `js/modules/security_trace.js` | `js/modules.js` |
| `js/modules/security_watch.js` | `js/modules/security.js` |
| `js/modules/security_watch_page.js` | `js/modules.js` |
| `js/modules/settings.js` | `js/modules.js` |
| `js/modules/sky.js` | `js/modules.js` |
| `js/modules/social.js` | `js/modules.js`, `js/modules/social_video.js` |
| `js/modules/social_video.js` | `js/modules/social.js` |
| `js/modules/status.js` | `js/modules.js` |
| `js/modules/synapses.js` | `js/modules.js` |
| `js/modules/today.js` | `js/modules.js` |
| `js/modules/trace.js` | `js/modules/chat.js` |
| `js/modules/updates.js` | `js/modules.js` |
| `js/modules/uploads.js` | `js/modules.js` |
| `js/modules/users.js` | `js/modules.js` |
| `js/mood.js` | `js/modules/alerts.js`, `js/modules/status.js` |
| `js/push.js` | `js/modules/alerts.js`, `js/modules/notifications.js` |
| `js/qr.js` | `js/main.js`, `js/modules/https.js`, `js/modules/users.js` |
| `js/restart.js` | `js/modules/autonomy.js`, `js/modules/autonomy_box.js`, `js/modules/firewall.js`, `js/modules/harvester.js`, `js/modules/models_choice.js`, `js/modules/models_mode.js`, `js/modules/plugins.js`, `js/modules/settings.js`, `js/modules/updates.js` |
| `js/share.js` | `js/modules/chat_media.js`, `js/modules/diary.js`, `js/modules/dreams.js` |
| `js/stack.js` | `js/main.js` |
| `js/style.js` | `js/main.js`, `js/modules/advanced.js`, `js/welcome.js` |
| `js/theme.js` | `js/main.js`, `js/style.js`, `js/welcome.js` |
| `js/vad.js` | `js/modules/chat.js`, `js/modules/chat_media.js` |
| `js/viewer.js` | `js/modules/chat.js`, `js/modules/chat_media.js`, `js/modules/diary.js`, `js/modules/dreams.js`, `js/modules/routines.js`, `js/modules/trace.js`, `js/modules/uploads.js` |
| `js/voice.js` | `js/main.js`, `js/modules/chat.js`, `js/modules/chat_media.js`, `js/modules/chat_menu.js` |
| `js/welcome.js` | `js/main.js` |
| `sw.js` | `js/main.js` |

## API routes: who calls them

Callers are found by the route's path in the WebUI, the scripts and the plugins; a route with nobody is called from outside (a phone, a client, a webhook) or by a path built at run time.

| route | served by | called by |
|---|---|---|
| POST `/v1/aurora/devices` | `api/access.py` | `script/svc_api.py`, `webui/js/api.js`, `webui/js/modules/settings.js` |
| GET `/v1/aurora/devices` | `api/access.py` | `script/svc_api.py`, `webui/js/api.js`, `webui/js/modules/settings.js` |
| DELETE `/v1/aurora/devices/{device_id}` | `api/access.py` | `script/svc_api.py`, `webui/js/modules/settings.js` |
| POST `/v1/aurora/logout` | `api/access.py` | `script/svc_api.py`, `webui/js/main.js`, `webui/js/modules/settings.js` |
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
| GET `/v1/aurora/memory/about-me` | `api/activity.py` | `webui/js/modules/memory.js` |
| DELETE `/v1/aurora/memory/about-me` | `api/activity.py` | `webui/js/modules/memory.js` |
| DELETE `/v1/aurora/memory/conversation` | `api/activity.py` | — |
| GET `/v1/aurora/reflections` | `api/activity.py` | `script/svc_api.py`, `webui/js/modules/diary.js`, `webui/js/modules/reports.js` |
| POST `/v1/aurora/agent` | `api/agents.py` | `script/bench_repair.py`, `script/svc_api.py`, `webui/js/modules/chat.js` |
| GET `/v1/aurora/plugins/signature` | `api/agents.py` | `webui/js/modules/plugins.js` |
| GET `/v1/aurora/plugins` | `api/agents.py` | `script/svc_api.py`, `webui/js/main.js`, `webui/js/modules/approvals.js`, `webui/js/modules/plugins.js`, `webui/js/modules/routines.js` |
| POST `/v1/aurora/plugins/{name}/{action}` | `api/agents.py` | `script/svc_api.py`, `webui/js/modules/plugins.js` |
| GET `/v1/aurora/plugins-trash` | `api/agents.py` | `webui/js/modules/plugins.js` |
| POST `/v1/aurora/plugins-trash/{item}/restore` | `api/agents.py` | `webui/js/modules/plugins.js` |
| GET `/v1/aurora/plugins/{name}/icon` | `api/agents.py` | `script/svc_api.py`, `webui/js/modules/plugins.js` |
| POST `/v1/aurora/plugins/{name}/icon` | `api/agents.py` | `script/svc_api.py`, `webui/js/modules/plugins.js` |
| POST `/v1/aurora/services/restart` | `api/agents.py` | `webui/js/modules/autonomy.js`, `webui/js/modules/autonomy_box.js`, `webui/js/modules/firewall.js`, `webui/js/modules/harvester.js`, `webui/js/restart.js` |
| POST `/v1/aurora/plugins/{name}/try/{tool}` | `api/agents.py` | `script/svc_api.py`, `webui/js/modules/plugins.js` |
| GET `/v1/aurora/approvals` | `api/agents.py` | `script/bench_repair.py`, `script/svc_api.py`, `webui/js/modules/alerts.js`, `webui/js/modules/approvals.js`, `webui/js/modules/social.js`, `webui/js/modules/today.js` |
| GET `/v1/aurora/approvals/stats` | `api/agents.py` | `webui/js/modules/approvals.js` |
| POST `/v1/aurora/approvals/{approval_id}/{decision}` | `api/agents.py` | `script/bench_repair.py`, `script/svc_api.py`, `webui/js/modules/approvals.js`, `webui/js/modules/social.js` |
| POST `/v1/aurora/rem/repair` | `api/agents.py` | `script/svc_api.py` |
| GET `/v1/aurora/autonomy` | `api/autonomy.py` | `webui/js/modules/autonomy.js`, `webui/js/modules/autonomy_box.js` |
| PUT `/v1/aurora/autonomy` | `api/autonomy.py` | `webui/js/modules/autonomy.js`, `webui/js/modules/autonomy_box.js` |
| PUT `/v1/aurora/autonomy/may-choose` | `api/autonomy.py` | `webui/js/modules/autonomy.js` |
| GET `/v1/aurora/backup` | `api/backup.py` | `webui/js/backup.js` |
| POST `/v1/aurora/backup/mount` | `api/backup.py` | `webui/js/backup.js` |
| GET `/v1/aurora/backup/snapshots` | `api/backup.py` | `webui/js/backup.js` |
| POST `/v1/aurora/backup/run` | `api/backup.py` | `webui/js/backup.js` |
| POST `/v1/aurora/bugreport` | `api/bugreport.py` | `webui/js/modules/bugreport.js` |
| GET `/v1/aurora/ideas` | `api/bugreport.py` | `webui/js/modules/ideas.js` |
| POST `/v1/aurora/ideas` | `api/bugreport.py` | `webui/js/modules/ideas.js` |
| PUT `/v1/aurora/ideas/{iid}` | `api/bugreport.py` | `webui/js/modules/ideas.js` |
| POST `/v1/aurora/ideas/{iid}/issue` | `api/bugreport.py` | `webui/js/modules/ideas.js` |
| GET `/v1/aurora/bugreports` | `api/bugreport.py` | `webui/js/modules/bugreport.js` |
| GET `/v1/aurora/bugreports/{name}` | `api/bugreport.py` | — |
| GET `/v1/aurora/calendar` | `api/calendar.py` | `webui/js/modules/calendar.js`, `webui/js/modules/today.js` |
| POST `/v1/aurora/calendar/items` | `api/calendar.py` | `webui/js/modules/calendar_form.js` |
| GET `/v1/aurora/calendar/items/{iid}` | `api/calendar.py` | `webui/js/modules/calendar.js`, `webui/js/modules/calendar_form.js` |
| PUT `/v1/aurora/calendar/items/{iid}` | `api/calendar.py` | `webui/js/modules/calendar.js`, `webui/js/modules/calendar_form.js` |
| DELETE `/v1/aurora/calendar/items/{iid}` | `api/calendar.py` | `webui/js/modules/calendar.js`, `webui/js/modules/calendar_form.js` |
| GET `/v1/aurora/calendar/pending` | `api/calendar.py` | `webui/js/calendar_alerts.js` |
| POST `/v1/aurora/calendar/answer` | `api/calendar.py` | `webui/js/calendar_alerts.js` |
| GET `/v1/aurora/calendar/export.ics` | `api/calendar.py` | `webui/js/modules/calendar.js` |
| POST `/v1/aurora/calendar/import` | `api/calendar.py` | `webui/js/modules/calendar.js` |
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
| GET `/v1/aurora/dj` | `api/dj.py` | `webui/js/modules/dj.js` |
| POST `/v1/aurora/dj/tracks` | `api/dj.py` | `webui/js/modules/dj.js` |
| DELETE `/v1/aurora/dj/{kind}/{name}` | `api/dj.py` | `webui/js/modules/dj.js` |
| GET `/v1/aurora/dj/{kind}/{name}` | `api/dj.py` | `webui/js/modules/dj.js` |
| POST `/v1/aurora/dj/make` | `api/dj.py` | `webui/js/modules/dj.js` |
| POST `/v1/aurora/documents/pdf` | `api/documents.py` | `webui/js/modules/trace.js` |
| GET `/v1/aurora/documents` | `api/documents.py` | `webui/js/modules/uploads.js` |
| GET `/v1/aurora/documents/{name}` | `api/documents.py` | `aurora/doc_preview.py`, `aurora/sys_routines.py`, `aurora/sys_uploads.py`, `sys/plugins/documents/plugin.json`, `webui/js/modules/trace.js` |
| DELETE `/v1/aurora/documents/{name}` | `api/documents.py` | `aurora/doc_preview.py`, `aurora/sys_routines.py`, `aurora/sys_uploads.py`, `sys/plugins/documents/plugin.json`, `webui/js/modules/trace.js` |
| GET `/v1/aurora/forge` | `api/forge.py` | `script/svc_api.py` |
| POST `/v1/aurora/forge/tick` | `api/forge.py` | `script/svc_api.py`, `script/svc_rem.py` |
| PUT `/v1/aurora/harvester/domains` | `api/harvester.py` | `script/svc_api.py`, `webui/js/modules/harvester.js` |
| GET `/v1/aurora/harvester` | `api/harvester.py` | `script/svc_api.py`, `webui/js/modules/harvester.js` |
| POST `/v1/aurora/harvester/{action}` | `api/harvester.py` | `script/svc_api.py`, `webui/js/modules/harvest_plan.js`, `webui/js/modules/harvester.js` |
| GET `/v1/aurora/home/devices` | `api/home.py` | `webui/js/modules/home.js`, `webui/js/modules/today.js`, `webui/js/welcome.js` |
| POST `/v1/aurora/home/service` | `api/home.py` | `webui/js/modules/home.js`, `webui/js/modules/today.js` |
| GET `/v1/aurora/home/camera/{entity_id}` | `api/home.py` | `webui/js/modules/home.js` |
| POST `/v1/aurora/home/look` | `api/home.py` | `webui/js/modules/home.js` |
| POST `/v1/aurora/home/agents/{device_id}` | `api/home.py` | `webui/js/modules/home.js` |
| GET `/v1/aurora/home/scenes` | `api/home.py` | `webui/js/modules/home_scenes.js` |
| POST `/v1/aurora/home/scenes` | `api/home.py` | `webui/js/modules/home_scenes.js` |
| POST `/v1/aurora/home/scenes/{name}/{action}` | `api/home.py` | `webui/js/modules/home_scenes.js` |
| GET `/v1/aurora/https` | `api/https.py` | `webui/js/modules/https.js` |
| PUT `/v1/aurora/https/cert` | `api/https.py` | `webui/js/modules/https.js` |
| DELETE `/v1/aurora/https/cert` | `api/https.py` | `webui/js/modules/https.js` |
| PUT `/v1/aurora/https/names` | `api/https.py` | `webui/js/modules/https.js` |
| PUT `/v1/aurora/https/ports` | `api/https.py` | `webui/js/modules/https.js` |
| POST `/v1/aurora/sentinel/incident` | `api/incidents.py` | `script/svc_api.py`, `script/svc_sentinel.py` |
| GET `/v1/aurora/incidents` | `api/incidents.py` | `script/svc_api.py`, `webui/js/modules/alerts.js`, `webui/js/modules/security.js` |
| POST `/v1/aurora/incidents/archive-closed` | `api/incidents.py` | `webui/js/modules/security.js` |
| GET `/v1/aurora/security/scorecard` | `api/incidents.py` | `webui/js/modules/security.js` |
| POST `/v1/aurora/incidents/{incident_id}/verdict` | `api/incidents.py` | `script/svc_api.py`, `webui/js/modules/security.js` |
| POST `/v1/aurora/incidents/{incident_id}/close` | `api/incidents.py` | `script/svc_api.py`, `webui/js/modules/security.js` |
| GET `/v1/aurora/domains` | `api/knowledge.py` | `script/kno_import.py`, `script/svc_api.py`, `webui/js/modules/import.js` |
| POST `/v1/aurora/import` | `api/knowledge.py` | `script/kno_import.py`, `script/svc_api.py`, `script/svc_harvester.py`, `script/vault_realign.py`, `webui/js/modules/import.js` |
| POST `/v1/aurora/solitons` | `api/knowledge.py` | `aurora/kno_dedup.py`, `script/kno_migrate_legacy.py`, `script/svc_api.py`, `script/svc_harvester.py` |
| DELETE `/v1/aurora/sources` | `api/knowledge.py` | `script/svc_api.py`, `script/vault_realign.py` |
| POST `/v1/aurora/memory/reset` | `api/knowledge.py` | `script/svc_api.py` |
| GET `/v1/aurora/history` | `api/knowledge.py` | `script/svc_api.py`, `webui/js/modules/chat.js` |
| GET `/v1/aurora/senses/devices` | `api/knowledge.py` | `script/svc_api.py`, `webui/js/modules/plugins.js` |
| POST `/v1/aurora/senses/{action}` | `api/knowledge.py` | `script/svc_api.py`, `webui/js/modules/chat.js`, `webui/js/modules/chat_media.js`, `webui/js/modules/plugins.js` |
| GET `/v1/aurora/features` | `api/knowledge.py` | `webui/js/modules/status.js` |
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
| GET `/v1/models` | `api/oai.py` | `aurora/mdl_formats.py`, `script/svc_api.py`, `webui/js/main.js` |
| POST `/v1/chat/completions` | `api/oai.py` | `aurora/mdl_llm.py`, `script/svc_api.py` |
| POST `/v1/aurora/oauth/{provider}/start` | `api/oauth.py` | `webui/js/main.js`, `webui/js/modules/plugins.js` |
| POST `/v1/aurora/oauth/finish` | `api/oauth.py` | `webui/js/main.js` |
| GET `/v1/aurora/places` | `api/places.py` | `webui/js/modules/plugins.js` |
| POST `/v1/aurora/artifacts/open` | `api/preview.py` | `webui/js/artifact.js` |
| GET `/v1/aurora/preview` | `api/preview.py` | `webui/js/viewer.js` |
| GET `/v1/aurora/preview/page` | `api/preview.py` | `webui/js/modules/uploads.js`, `webui/js/viewer.js` |
| GET `/v1/aurora/projects` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/github` | `api/projects.py` | `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/tree` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/file` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/reports` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/log` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/preview` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/preview/{token}/{path:path}` | `api/projects.py` | `aurora/doc_artifact.py`, `aurora/net_https.py`, `script/svc_api.py`, `webui/js/artifact.js` |
| POST `/v1/aurora/projects` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/clone` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/terminal` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/terminal/{sid}/stream` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/terminal/{sid}/input` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| DELETE `/v1/aurora/projects/{name}/terminal/{sid}` | `api/projects.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/plan` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/plan` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| PUT `/v1/aurora/projects/{name}/plan` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/docs` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| POST `/v1/aurora/projects/{name}/docs` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
| GET `/v1/aurora/projects/{name}/pdf` | `api/projects_plan.py` | `script/svc_api.py`, `webui/js/modules/project_docs.js`, `webui/js/modules/project_plan.js`, `webui/js/modules/project_term.js`, `webui/js/modules/projects.js` |
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
| GET `/v1/aurora/routines` | `api/routines.py` | `script/svc_api.py`, `webui/js/modules/routines.js` |
| POST `/v1/aurora/routines` | `api/routines.py` | `script/svc_api.py`, `webui/js/modules/routines.js` |
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
| POST `/v1/aurora/ask` | `api/runs.py` | `script/bench_agi.py`, `script/bench_memory_days.py`, `script/bench_public.py`, `script/bench_quality.py`, `script/shadow_seed.py`, `script/svc_api.py`, `webui/js/modules/chat.js` |
| POST `/v1/aurora/shadow/import` | `api/runs.py` | `script/shadow_seed.py` |
| POST `/v1/aurora/acquire` | `api/runs.py` | `script/svc_api.py`, `webui/js/modules/chat.js` |
| GET `/v1/aurora/runs` | `api/runs.py` | `script/bench_preflight.py`, `script/bench_repair.py`, `script/svc_api.py`, `webui/js/modules/bugreport.js`, `webui/js/modules/runs.js`, `webui/js/modules/social_video.js` |
| GET `/v1/aurora/runs/{run_id}/events` | `api/runs.py` | `script/bench_agi.py`, `script/bench_memory_days.py`, `script/bench_quality.py`, `script/shadow_seed.py`, `script/svc_api.py`, `webui/js/api.js` |
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
| GET `/v1/aurora/social` | `api/social.py` | `script/svc_api.py`, `webui/js/modules/social.js` |
| POST `/v1/aurora/social/draft` | `api/social.py` | `script/svc_api.py`, `webui/js/modules/social.js` |
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
| GET `/v1/aurora/settings` | `api/system.py` | `script/svc_api.py`, `sys/plugins/dropbox/authorize.py`, `sys/plugins/tiktok/authorize.py`, `webui/js/modules/care_diet.js`, `webui/js/modules/firewall.js`, `webui/js/modules/harvester.js`, `webui/js/modules/plugins.js`, `webui/js/modules/settings.js`, `webui/js/modules/updates.js`, `webui/js/modules/users.js`, `webui/js/welcome.js` |
| POST `/v1/aurora/settings/factory` | `api/system.py` | `webui/js/modules/settings.js` |
| GET `/v1/aurora/factory` | `api/system.py` | `webui/js/modules/settings.js` |
| POST `/v1/aurora/factory/mind` | `api/system.py` | `webui/js/modules/settings.js` |
| PUT `/v1/aurora/settings` | `api/system.py` | `script/svc_api.py`, `sys/plugins/dropbox/authorize.py`, `sys/plugins/tiktok/authorize.py`, `webui/js/modules/care_diet.js`, `webui/js/modules/firewall.js`, `webui/js/modules/harvester.js`, `webui/js/modules/plugins.js`, `webui/js/modules/settings.js`, `webui/js/modules/updates.js`, `webui/js/modules/users.js`, `webui/js/welcome.js` |
| GET `/v1/aurora/update` | `api/updates.py` | `script/svc_api.py`, `webui/js/modules/updates.js` |
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
| POST `/v1/aurora/login` | `api/users.py` | `script/bench_memory_days.py`, `webui/js/main.js` |
| GET `/v1/aurora/me` | `api/users.py` | `script/bench_memory_days.py`, `webui/js/main.js`, `webui/js/modules/plugins.js`, `webui/js/modules/users.js` |
| PUT `/v1/aurora/me/prefs` | `api/users.py` | `webui/js/style.js`, `webui/js/theme.js` |
| POST `/v1/aurora/me/welcomed` | `api/users.py` | `webui/js/welcome.js` |
| POST `/v1/aurora/me/password` | `api/users.py` | `webui/js/modules/users.js` |
| POST `/v1/aurora/me/totp` | `api/users.py` | `webui/js/modules/users.js` |
| GET `/v1/aurora/me/keys` | `api/users.py` | `webui/js/modules/users.js` |
| POST `/v1/aurora/me/keys` | `api/users.py` | `webui/js/modules/users.js` |
| DELETE `/v1/aurora/me/keys/{key_id}` | `api/users.py` | `webui/js/modules/users.js` |
| GET `/v1/aurora/users` | `api/users.py` | `webui/js/modules/users.js` |
| POST `/v1/aurora/users` | `api/users.py` | `webui/js/modules/users.js` |
| POST `/v1/aurora/users/{name}/password` | `api/users.py` | `webui/js/modules/users.js` |
| POST `/v1/aurora/users/{name}/totp-reset` | `api/users.py` | `webui/js/modules/users.js` |
| DELETE `/v1/aurora/users/{name}` | `api/users.py` | `webui/js/modules/users.js` |
| GET `/v1/aurora/tts` | `api/voice.py` | `webui/js/voice.js` |
| POST `/v1/aurora/tts` | `api/voice.py` | `webui/js/voice.js` |

Modules nobody in the code imports: 0; routes nobody in the repository names: 5 of 282.
