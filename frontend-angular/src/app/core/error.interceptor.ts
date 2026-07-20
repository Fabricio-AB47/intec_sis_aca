import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { catchError, throwError } from 'rxjs';

export const errorInterceptor: HttpInterceptorFn = (request, next) => {
  const snackBar = inject(MatSnackBar);
  return next(request).pipe(
    catchError((error: HttpErrorResponse) => {
      const message =
        error.error?.detail ||
        error.error?.message ||
        error.message ||
        'No se pudo completar la operación.';
      snackBar.open(message, 'Cerrar', { duration: 6000 });
      return throwError(() => error);
    })
  );
};
