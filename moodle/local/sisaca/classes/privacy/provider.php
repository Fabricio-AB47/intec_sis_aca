<?php
// This file is part of Moodle - http://moodle.org/.

namespace local_sisaca\privacy;

defined('MOODLE_INTERNAL') || die();

/**
 * El complemento opera sobre fechas existentes y no conserva datos propios.
 */
class provider implements \core_privacy\local\metadata\null_provider {
    /**
     * Explica por que el complemento no registra datos personales.
     */
    public static function get_reason(): string {
        return 'privacy:metadata';
    }
}
