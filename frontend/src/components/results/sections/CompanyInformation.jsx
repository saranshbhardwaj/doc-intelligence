// src/components/results/sections/CompanyInformation.jsx
import { Building2 } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";

export default function CompanyInformation({ data }) {
  const company = data.company_info;

  if (!company) {
    return null;
  }

  return (
    <Section title="Company Information" icon={Building2}>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {company.company_name && (
          <DataField label="Company Name" value={company.company_name} />
        )}
        {company.company_id && (
          <DataField label="Company ID" value={company.company_id} />
        )}
        {company.industry && (
          <DataField label="Industry" value={company.industry} />
        )}
        {company.secondary_industry && (
          <DataField
            label="Secondary Industry"
            value={company.secondary_industry}
          />
        )}
        {company.founded_year && (
          <DataField
            label="Founded"
            value={company.founded_year}
            format="number"
          />
        )}
        {company.employees && (
          <DataField
            label="Employees"
            value={company.employees}
            format="number"
          />
        )}
        {company.headquarters && (
          <DataField label="Headquarters" value={company.headquarters} />
        )}
        {company.website && (
          <DataField label="Website" value={company.website} />
        )}
        {company.business_structure && (
          <DataField
            label="Business Structure"
            value={company.business_structure}
          />
        )}
      </div>
    </Section>
  );
}
