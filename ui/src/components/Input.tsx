import { InputHTMLAttributes, TextareaHTMLAttributes, SelectHTMLAttributes, ReactNode } from 'react';
import Icon from './Icon';
import './Input.css';

// Base props shared by all input types
interface BaseInputProps {
  label?: string;
  error?: string;
  hint?: string;
  required?: boolean;
  success?: boolean;
  tooltip?: string;
}

// TextInput component
export interface TextInputProps extends InputHTMLAttributes<HTMLInputElement>, BaseInputProps {
  icon?: ReactNode;
  showCharCount?: boolean;
}

export function TextInput({
  label,
  error,
  hint,
  required = false,
  success = false,
  tooltip,
  icon,
  showCharCount = false,
  className = '',
  ...rest
}: TextInputProps) {
  const inputId = rest.id || `input-${Math.random().toString(36).substring(2, 11)}`;
  const showValidationIcon = !rest.disabled && (error || success);
  const charCount = typeof rest.value === 'string' ? rest.value.length : 0;
  const maxLength = typeof rest.maxLength === 'number' ? rest.maxLength : undefined;
  const shouldShowCharCount = Boolean(showCharCount && maxLength);
  const errorId = error ? `${inputId}-error` : undefined;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const describedBy = error ? errorId : !error && hint ? hintId : undefined;

  return (
    <div className={`input-group ${className}`}>
      {label && (
        <label htmlFor={inputId} className="input-label">
          {label}
          {required && <span className="input-required">*</span>}
          {tooltip && (
            <span className="input-tooltip" title={tooltip} aria-hidden="true">
              <Icon type="info-circle" size={14} />
            </span>
          )}
        </label>
      )}
      <div className="input-wrapper">
        {icon && <span className="input-icon">{icon}</span>}
        <input
          id={inputId}
          className={`input ${error ? 'input-error' : ''} ${success ? 'input-success' : ''} ${icon ? 'input-with-icon' : ''} ${showValidationIcon ? 'input-with-validation' : ''}`}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={describedBy}
          {...rest}
        />
        {showValidationIcon && (
          <span className={`input-validation-icon ${error ? 'validation-error' : 'validation-success'}`}>
            {error ? (
              <Icon type="x-circle" size={16} />
            ) : (
              <Icon type="check-circle" size={16} />
            )}
          </span>
        )}
      </div>
      {shouldShowCharCount ? (
        <div className="input-meta-row">
          {error ? (
            <span id={errorId} className="input-error-text">
              {error}
            </span>
          ) : hint ? (
            <span id={hintId} className="input-hint">
              {hint}
            </span>
          ) : (
            <span className="input-hint" aria-hidden="true">&nbsp;</span>
          )}
          <span className="char-count">
            {charCount}/{maxLength}
          </span>
        </div>
      ) : (
        <>
          {error && (
            <span id={errorId} className="input-error-text">
              {error}
            </span>
          )}
          {hint && !error && (
            <span id={hintId} className="input-hint">
              {hint}
            </span>
          )}
        </>
      )}
    </div>
  );
}

// TextArea component
export interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement>, BaseInputProps {
  rows?: number;
  maxLength?: number;
  showCharCount?: boolean;
}

export function TextArea({
  label,
  error,
  hint,
  required = false,
  success = false,
  tooltip,
  rows = 4,
  maxLength,
  showCharCount = false,
  className = '',
  value,
  ...rest
}: TextAreaProps) {
  const inputId = rest.id || `textarea-${Math.random().toString(36).substring(2, 11)}`;
  const charCount = typeof value === 'string' ? value.length : 0;

  return (
    <div className={`input-group ${className}`}>
      {label && (
        <label htmlFor={inputId} className="input-label">
          {label}
          {required && <span className="input-required">*</span>}
          {tooltip && (
            <span className="input-tooltip" title={tooltip} aria-hidden="true">
              <Icon type="info-circle" size={14} />
            </span>
          )}
        </label>
      )}
      <textarea
        id={inputId}
        rows={rows}
        maxLength={maxLength}
        className={`textarea ${error ? 'input-error' : ''} ${success ? 'input-success' : ''}`}
        aria-invalid={error ? 'true' : 'false'}
        aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
        value={value}
        {...rest}
      />
      <div className="input-meta-row">
        {error && (
          <span id={`${inputId}-error`} className="input-error-text">
            {error}
          </span>
        )}
        {hint && !error && (
          <span id={`${inputId}-hint`} className="input-hint">
            {hint}
          </span>
        )}
        {showCharCount && maxLength && (
          <span className="char-count">
            {charCount}/{maxLength}
          </span>
        )}
      </div>
    </div>
  );
}

// Select component
export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement>, BaseInputProps {
  options?: Array<{ value: string; label: string; disabled?: boolean }>;
  placeholder?: string;
}

export function Select({
  label,
  error,
  hint,
  required = false,
  success = false,
  tooltip,
  options = [],
  placeholder,
  className = '',
  children,
  ...rest
}: SelectProps) {
  const inputId = rest.id || `select-${Math.random().toString(36).substring(2, 11)}`;

  return (
    <div className={`input-group ${className}`}>
      {label && (
        <label htmlFor={inputId} className="input-label">
          {label}
          {required && <span className="input-required">*</span>}
          {tooltip && (
            <span className="input-tooltip" title={tooltip} aria-hidden="true">
              <Icon type="info-circle" size={14} />
            </span>
          )}
        </label>
      )}
      <select
        id={inputId}
        className={`select ${error ? 'input-error' : ''} ${success ? 'input-success' : ''}`}
        aria-invalid={error ? 'true' : 'false'}
        aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
        {...rest}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.length > 0
          ? options.map((option) => (
              <option key={option.value} value={option.value} disabled={option.disabled}>
                {option.label}
              </option>
            ))
          : children}
      </select>
      {error && (
        <span id={`${inputId}-error`} className="input-error-text">
          {error}
        </span>
      )}
      {hint && !error && (
        <span id={`${inputId}-hint`} className="input-hint">
          {hint}
        </span>
      )}
    </div>
  );
}
