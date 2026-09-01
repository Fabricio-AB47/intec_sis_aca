<?php
// This file is part of Moodle - http://moodle.org/.

defined('MOODLE_INTERNAL') || die();

global $CFG;
require_once($CFG->libdir . '/externallib.php');
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->dirroot . '/mod/assign/lib.php');
require_once($CFG->dirroot . '/mod/quiz/lib.php');

use core_external\external_api;
use core_external\external_function_parameters;
use core_external\external_multiple_structure;
use core_external\external_single_structure;
use core_external\external_value;

/**
 * Funciones externas de la integracion SISACA.
 */
class local_sisaca_external extends external_api {
    /**
     * Parametros de la actualizacion masiva.
     */
    public static function bulk_update_evaluation_dates_parameters(): external_function_parameters {
        return new external_function_parameters([
            'courseid' => new external_value(PARAM_INT, 'Identificador del curso.'),
            'updates' => new external_multiple_structure(
                new external_single_structure([
                    'cmid' => new external_value(PARAM_INT, 'Identificador del modulo del curso.'),
                    'modname' => new external_value(PARAM_ALPHA, 'Tipo de actividad: assign o quiz.'),
                    'instance' => new external_value(PARAM_INT, 'Identificador de la instancia.'),
                    'allowsubmissionsfromdate' => new external_value(
                        PARAM_INT,
                        'Fecha de apertura de la tarea.',
                        VALUE_OPTIONAL
                    ),
                    'duedate' => new external_value(
                        PARAM_INT,
                        'Fecha de entrega de la tarea.',
                        VALUE_OPTIONAL
                    ),
                    'cutoffdate' => new external_value(
                        PARAM_INT,
                        'Fecha de cierre definitivo de la tarea.',
                        VALUE_OPTIONAL
                    ),
                    'timeopen' => new external_value(
                        PARAM_INT,
                        'Fecha de apertura del cuestionario.',
                        VALUE_OPTIONAL
                    ),
                    'timeclose' => new external_value(
                        PARAM_INT,
                        'Fecha de cierre del cuestionario.',
                        VALUE_OPTIONAL
                    ),
                ]),
                'Actividades que se actualizaran.'
            ),
        ]);
    }

    /**
     * Valida que las fechas mantengan un orden cronologico correcto.
     */
    private static function validate_date_order(string $modname, stdClass $record): void {
        if ($modname === 'assign') {
            $open = (int)$record->allowsubmissionsfromdate;
            $due = (int)$record->duedate;
            $cutoff = (int)$record->cutoffdate;
            if ($open > 0 && $due > 0 && $open > $due) {
                throw new invalid_parameter_exception(
                    'La apertura de una tarea no puede ser posterior a su fecha de entrega.'
                );
            }
            if ($due > 0 && $cutoff > 0 && $due > $cutoff) {
                throw new invalid_parameter_exception(
                    'La fecha de entrega no puede ser posterior al cierre definitivo.'
                );
            }
            if ($open > 0 && $cutoff > 0 && $open > $cutoff) {
                throw new invalid_parameter_exception(
                    'La apertura de una tarea no puede ser posterior al cierre definitivo.'
                );
            }
            return;
        }

        $open = (int)$record->timeopen;
        $close = (int)$record->timeclose;
        if ($open > 0 && $close > 0 && $open > $close) {
            throw new invalid_parameter_exception(
                'La apertura de un cuestionario no puede ser posterior a su cierre.'
            );
        }
    }

    /**
     * Actualiza tareas y cuestionarios despues de verificar su identidad y curso.
     *
     * @param int $courseid
     * @param array $updates
     * @return array
     */
    public static function bulk_update_evaluation_dates(int $courseid, array $updates): array {
        global $DB;

        $params = self::validate_parameters(
            self::bulk_update_evaluation_dates_parameters(),
            ['courseid' => $courseid, 'updates' => $updates]
        );
        $courseid = (int)$params['courseid'];
        $updates = $params['updates'];
        if (count($updates) > 500) {
            throw new invalid_parameter_exception(
                'Una operacion admite como maximo 500 actividades.'
            );
        }

        $course = $DB->get_record('course', ['id' => $courseid], '*', MUST_EXIST);
        $coursecontext = context_course::instance($courseid);
        self::validate_context($coursecontext);
        require_capability('moodle/course:manageactivities', $coursecontext);

        $allowedfields = [
            'assign' => ['allowsubmissionsfromdate', 'duedate', 'cutoffdate'],
            'quiz' => ['timeopen', 'timeclose'],
        ];
        $seen = [];
        $updated = 0;
        $transaction = $DB->start_delegated_transaction();

        foreach ($updates as $update) {
            $cmid = (int)$update['cmid'];
            $modname = core_text::strtolower(trim((string)$update['modname']));
            $instance = (int)$update['instance'];
            if (!array_key_exists($modname, $allowedfields)) {
                throw new invalid_parameter_exception(
                    'Solo se pueden actualizar tareas y cuestionarios.'
                );
            }
            if (isset($seen[$cmid])) {
                throw new invalid_parameter_exception(
                    'La misma actividad no puede aparecer dos veces en una operacion.'
                );
            }
            $seen[$cmid] = true;

            $cm = get_coursemodule_from_id($modname, $cmid, $courseid, false, MUST_EXIST);
            if ((int)$cm->instance !== $instance || (int)$cm->course !== $courseid) {
                throw new invalid_parameter_exception(
                    'La actividad enviada no coincide con el curso o la instancia de Moodle.'
                );
            }
            $modulecontext = context_module::instance($cmid);
            self::validate_context($modulecontext);
            require_capability('moodle/course:manageactivities', $modulecontext);

            $record = $DB->get_record($modname, ['id' => $instance], '*', MUST_EXIST);
            if ((int)$record->course !== $courseid) {
                throw new invalid_parameter_exception(
                    'La instancia de la actividad no pertenece al curso indicado.'
                );
            }

            $changed = false;
            foreach ($allowedfields[$modname] as $field) {
                if (!array_key_exists($field, $update)) {
                    continue;
                }
                $value = (int)$update[$field];
                if ($value < 0 || $value > 4102444799) {
                    throw new invalid_parameter_exception(
                        'Una de las fechas esta fuera del rango permitido.'
                    );
                }
                if ((int)$record->{$field} !== $value) {
                    $record->{$field} = $value;
                    $changed = true;
                }
            }
            if (!$changed) {
                continue;
            }

            self::validate_date_order($modname, $record);
            $record->timemodified = time();
            $DB->update_record($modname, $record);
            if ($modname === 'assign') {
                assign_refresh_events($courseid, $record, $cm);
            } else {
                quiz_refresh_events($courseid, $record, $cm);
            }

            $event = \core\event\course_module_updated::create_from_cm($cm, $modulecontext);
            $event->add_record_snapshot($modname, $record);
            $event->trigger();
            $updated++;
        }

        if ($updated > 0) {
            rebuild_course_cache($courseid, true);
        }
        $transaction->allow_commit();

        return ['updatedcount' => $updated];
    }

    /**
     * Estructura de la respuesta.
     */
    public static function bulk_update_evaluation_dates_returns(): external_single_structure {
        return new external_single_structure([
            'updatedcount' => new external_value(PARAM_INT, 'Numero de actividades actualizadas.'),
        ]);
    }
}
