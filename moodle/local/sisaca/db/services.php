<?php
// This file is part of Moodle - http://moodle.org/.

defined('MOODLE_INTERNAL') || die();

$functions = [
    'local_sisaca_bulk_update_evaluation_dates' => [
        'classname' => 'local_sisaca_external',
        'methodname' => 'bulk_update_evaluation_dates',
        'classpath' => 'local/sisaca/externallib.php',
        'description' => 'Actualiza de forma controlada las fechas de tareas y cuestionarios de un curso.',
        'type' => 'write',
        'capabilities' => 'moodle/course:manageactivities',
        'ajax' => false,
    ],
];

// Este servicio independiente permite emitir un token exclusivo si no se desea
// incorporar la funcion al servicio institucional SIS_ACA.
$services = [
    'SISACA - Fechas de evaluaciones' => [
        'functions' => ['local_sisaca_bulk_update_evaluation_dates'],
        'restrictedusers' => 1,
        'enabled' => 1,
        'shortname' => 'local_sisaca_dates',
        'downloadfiles' => 0,
        'uploadfiles' => 0,
    ],
];
