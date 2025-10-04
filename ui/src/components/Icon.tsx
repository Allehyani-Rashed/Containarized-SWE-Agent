/**
 * Icon Component
 *
 * Professional SVG icon library for the application.
 * All icons default to 20x20 size and inherit color from parent.
 */

import React from 'react';

export type IconType =
  | 'edit'
  | 'clipboard'
  | 'folder'
  | 'chart'
  | 'settings'
  | 'help'
  | 'rocket'
  | 'key'
  | 'trash'
  | 'check'
  | 'alert'
  | 'clock'
  | 'plug'
  | 'bell'
  | 'info'
  | 'robot'
  | 'chevron-down'
  | 'chevron-up'
  | 'eye'
  | 'copy'
  | 'rotate-cw'
  | 'home'
  | 'chevron-right'
  | 'info-circle'
  | 'x-circle'
  | 'check-circle';

interface IconProps {
  type: IconType;
  size?: number;
  className?: string;
  style?: React.CSSProperties;
}

function Icon({ type, size = 20, className = '', style = {} }: IconProps) {
  const baseProps = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    className,
    style,
  };

  switch (type) {
    case 'edit':
      // Pencil icon for Submit Task / Edit
      return (
        <svg {...baseProps}>
          <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
        </svg>
      );

    case 'clipboard':
      // Clipboard/List icon for Tasks
      return (
        <svg {...baseProps}>
          <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
          <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
          <line x1="9" y1="12" x2="15" y2="12" />
          <line x1="9" y1="16" x2="15" y2="16" />
        </svg>
      );

    case 'folder':
      // Folder icon for Projects
      return (
        <svg {...baseProps}>
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        </svg>
      );

    case 'chart':
      // Bar chart icon for Analytics
      return (
        <svg {...baseProps}>
          <line x1="12" y1="20" x2="12" y2="10" />
          <line x1="18" y1="20" x2="18" y2="4" />
          <line x1="6" y1="20" x2="6" y2="16" />
        </svg>
      );

    case 'settings':
      // Gear icon for Settings
      return (
        <svg {...baseProps}>
          <circle cx="12" cy="12" r="3" />
          <path d="M12 1v6m0 6v6M5.64 5.64l4.24 4.24m4.24 4.24l4.24 4.24M1 12h6m6 0h6M5.64 18.36l4.24-4.24m4.24-4.24l4.24-4.24" />
        </svg>
      );

    case 'help':
      // Question mark icon for Help
      return (
        <svg {...baseProps}>
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      );

    case 'rocket':
      // Rocket icon for Create Task
      return (
        <svg {...baseProps}>
          <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z" />
          <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" />
          <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
          <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
        </svg>
      );

    case 'key':
      // Key icon for credentials
      return (
        <svg {...baseProps}>
          <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
        </svg>
      );

    case 'trash':
      // Trash bin icon for delete
      return (
        <svg {...baseProps}>
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          <line x1="10" y1="11" x2="10" y2="17" />
          <line x1="14" y1="11" x2="14" y2="17" />
        </svg>
      );

    case 'check':
      // Checkmark icon for success/verify
      return (
        <svg {...baseProps}>
          <polyline points="20 6 9 17 4 12" />
        </svg>
      );

    case 'alert':
      // Alert/Warning triangle icon
      return (
        <svg {...baseProps}>
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      );

    case 'clock':
      // Clock icon for time/duration
      return (
        <svg {...baseProps}>
          <circle cx="12" cy="12" r="10" />
          <polyline points="12 6 12 12 16 14" />
        </svg>
      );

    case 'plug':
      // Plug icon for API/connectivity
      return (
        <svg {...baseProps}>
          <path d="M12 2v4m0 12v4M6 6h12M6 18h12M5 10h14M5 14h14" />
        </svg>
      );

    case 'bell':
      // Bell icon for alerts/notifications
      return (
        <svg {...baseProps}>
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
      );

    case 'info':
      // Info icon
      return (
        <svg {...baseProps}>
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
      );

    case 'robot':
      // Robot icon for AI/automation
      return (
        <svg {...baseProps}>
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          <line x1="9" y1="15" x2="9.01" y2="15" />
          <line x1="15" y1="15" x2="15.01" y2="15" />
        </svg>
      );

    case 'chevron-down':
      // Chevron down for expand
      return (
        <svg {...baseProps}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      );

    case 'chevron-up':
      // Chevron up for collapse
      return (
        <svg {...baseProps}>
          <polyline points="18 15 12 9 6 15" />
        </svg>
      );

    case 'eye':
      // Eye icon for view/preview
      return (
        <svg {...baseProps}>
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );

    case 'copy':
      // Copy/duplicate icon
      return (
        <svg {...baseProps}>
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      );

    case 'rotate-cw':
      // Rotate clockwise icon for retry/refresh
      return (
        <svg {...baseProps}>
          <polyline points="23 4 23 10 17 10" />
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
        </svg>
      );

    case 'home':
      // Home icon for breadcrumbs
      return (
        <svg {...baseProps} viewBox="0 0 16 16">
          <path d="M2 6l6-4.5L14 6v7a1 1 0 01-1 1H3a1 1 0 01-1-1V6z" />
          <path d="M6 13V9h4v4" />
        </svg>
      );

    case 'chevron-right':
      // Chevron right for breadcrumb separator
      return (
        <svg {...baseProps} viewBox="0 0 16 16">
          <path d="M6 12l4-4-4-4" />
        </svg>
      );

    case 'info-circle':
      // Info circle icon for tooltips (filled version)
      return (
        <svg {...baseProps} viewBox="0 0 16 16" fill="currentColor" stroke="none">
          <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/>
          <path d="m8.93 6.588-2.29.287-.082.38.45.083c.294.07.352.176.288.469l-.738 3.468c-.194.897.105 1.319.808 1.319.545 0 1.178-.252 1.465-.598l.088-.416c-.2.176-.492.246-.686.246-.275 0-.375-.193-.304-.533L8.93 6.588zM9 4.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
        </svg>
      );

    case 'x-circle':
      // X circle icon for validation errors (filled version)
      return (
        <svg {...baseProps} viewBox="0 0 16 16" fill="currentColor" stroke="none">
          <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/>
          <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
        </svg>
      );

    case 'check-circle':
      // Check circle icon for validation success (filled version)
      return (
        <svg {...baseProps} viewBox="0 0 16 16" fill="currentColor" stroke="none">
          <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/>
          <path d="M10.97 4.97a.235.235 0 0 0-.02.022L7.477 9.417 5.384 7.323a.75.75 0 0 0-1.06 1.06L6.97 11.03a.75.75 0 0 0 1.079-.02l3.992-4.99a.75.75 0 0 0-1.071-1.05z"/>
        </svg>
      );

    default:
      return null;
  }
}

export default Icon;
