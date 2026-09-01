<?php
// This file is part of Moodle - http://moodle.org/.

defined('MOODLE_INTERNAL') || die();

/**
 * Incorpora la funcion al servicio institucional existente sin reemplazarlo.
 */
function xmldb_local_sisaca_install(): void {
    global $DB;

    $functionname = 'local_sisaca_bulk_update_evaluation_dates';
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

        $params = [
            'externalserviceid' => (int)$service->id,
            'functionname' => $functionname,
        ];
        if (!$DB->record_exists('external_services_functions', $params)) {
            $DB->insert_record('external_services_functions', (object)$params);
        }
    }
}
