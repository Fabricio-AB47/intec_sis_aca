<?php
// This file is part of Moodle - http://moodle.org/.

defined('MOODLE_INTERNAL') || die();

/**
 * Actualizaciones del plugin local SISACA.
 */
function xmldb_local_sisaca_upgrade(int $oldversion): bool {
    global $DB;

    if ($oldversion < 2026090100) {
        $functionnames = [
            'local_sisaca_bulk_update_evaluation_dates',
            'local_sisaca_get_editable_course_content',
            'local_sisaca_update_html_content',
        ];
        $services = $DB->get_records('external_services', ['enabled' => 1]);
        foreach ($services as $service) {
            $identity = implode(' ', [
                (string)($service->shortname ?? ''),
                (string)($service->name ?? ''),
            ]);
            $identity = core_text::strtolower($identity);
            $identity = preg_replace('/[^a-z0-9]+/', '', $identity);
            if (strpos($identity, 'sisaca') === false) {
                continue;
            }
            foreach ($functionnames as $functionname) {
                $params = [
                    'externalserviceid' => (int)$service->id,
                    'functionname' => $functionname,
                ];
                if (!$DB->record_exists('external_services_functions', $params)) {
                    $DB->insert_record('external_services_functions', (object)$params);
                }
            }
        }

        upgrade_plugin_savepoint(true, 2026090100, 'local', 'sisaca');
    }

    return true;
}
