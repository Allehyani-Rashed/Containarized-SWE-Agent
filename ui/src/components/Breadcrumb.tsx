import { Link } from 'react-router-dom';
import Icon from './Icon';
import './Breadcrumb.css';

export interface BreadcrumbItem {
  label: string;
  path?: string;
}

export interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

function Breadcrumb({ items }: BreadcrumbProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <nav className="breadcrumb" aria-label="Breadcrumb">
      <ol className="breadcrumb-list">
        {items.map((item, index) => {
          const isLast = index === items.length - 1;

          return (
            <li key={item.path || `breadcrumb-${item.label}-${index}`} className="breadcrumb-item">
              {!isLast && item.path ? (
                <>
                  <Link to={item.path} className="breadcrumb-link">
                    {index === 0 && (
                      <Icon type="home" size={16} className="breadcrumb-home-icon" />
                    )}
                    <span className="breadcrumb-label">{item.label}</span>
                  </Link>
                  <Icon type="chevron-right" size={16} className="breadcrumb-separator" />
                </>
              ) : (
                <span className="breadcrumb-current" aria-current="page">
                  {index === 0 && (
                    <Icon type="home" size={16} className="breadcrumb-home-icon" />
                  )}
                  <span className="breadcrumb-label">{item.label}</span>
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export default Breadcrumb;
