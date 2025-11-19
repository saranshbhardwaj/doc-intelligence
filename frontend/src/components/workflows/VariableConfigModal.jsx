/**
 * Variable Configuration Modal
 *
 * Professional modal for configuring workflow variables
 * Uses shadcn Dialog for responsive design
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Checkbox } from "../ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

export default function VariableConfigModal({
  open,
  onOpenChange,
  template,
  variables,
  onVariablesChange,
  onGenerate,
}) {
  if (!template) return null;

  const handleVariableChange = (name, value, type) => {
    let parsedValue = value;

    if (type === "integer") {
      parsedValue = parseInt(value, 10) || 0;
    } else if (type === "number") {
      parsedValue = parseFloat(value) || 0;
    } else if (type === "boolean") {
      parsedValue = value === "true" || value === true;
    }

    onVariablesChange({ ...variables, [name]: parsedValue });
  };

  const renderVariableInput = (varDef) => {
    const { name, type, required, choices, min, max, description } = varDef;
    const value = variables[name] ?? "";

    if (type === "enum") {
      return (
        <Select
          value={value}
          onValueChange={(val) => handleVariableChange(name, val, type)}
        >
          <SelectTrigger>
            <SelectValue placeholder={`Select ${name}`} />
          </SelectTrigger>
          <SelectContent>
            {(choices || []).map((choice) => (
              <SelectItem key={choice} value={choice}>
                {choice}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    } else if (type === "boolean") {
      return (
        <div className="flex items-center gap-2">
          <Checkbox
            id={name}
            checked={value === true}
            onCheckedChange={(checked) =>
              handleVariableChange(name, checked, type)
            }
          />
          <Label htmlFor={name} className="text-sm font-normal cursor-pointer">
            {value ? "Enabled" : "Disabled"}
          </Label>
        </div>
      );
    } else if (type === "integer" || type === "number") {
      return (
        <Input
          type="number"
          value={value}
          onChange={(e) => handleVariableChange(name, e.target.value, type)}
          min={min}
          max={max}
          step={type === "integer" ? 1 : 0.1}
        />
      );
    } else {
      return (
        <Input
          type="text"
          value={value}
          onChange={(e) => handleVariableChange(name, e.target.value, type)}
          placeholder={description || `Enter ${name}`}
        />
      );
    }
  };

  const variablesSchema = template.variables_schema || [];
  const requiredVars = variablesSchema.filter((v) => v.required);
  const missingRequired = requiredVars.filter(
    (v) =>
      !(v.name in variables) ||
      variables[v.name] === null ||
      variables[v.name] === ""
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl">
            Configure {template.name}
          </DialogTitle>
          <DialogDescription>
            Fill in the required fields and customize optional parameters below
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {variablesSchema.length === 0 ? (
            <p className="text-sm text-muted-foreground dark:text-muted-foreground text-center py-8">
              This workflow has no configurable variables
            </p>
          ) : (
            <>
              {/* Required Variables */}
              {requiredVars.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
                    <span className="text-red-600">*</span> Required Fields
                  </h4>
                  <div className="space-y-4">
                    {requiredVars.map((varDef) => (
                      <div key={varDef.name}>
                        <Label
                          htmlFor={varDef.name}
                          className="flex items-center gap-2 mb-2"
                        >
                          <span className="capitalize">
                            {varDef.name.replace(/_/g, " ")}
                          </span>
                          <span className="text-red-600">*</span>
                        </Label>
                        {renderVariableInput(varDef)}
                        {varDef.description && (
                          <p className="mt-1 text-xs text-muted-foreground dark:text-muted-foreground">
                            {varDef.description}
                          </p>
                        )}
                        {(varDef.type === "integer" ||
                          varDef.type === "number") &&
                          (varDef.min !== undefined ||
                            varDef.max !== undefined) && (
                            <p className="mt-1 text-xs text-muted-foreground dark:text-muted-foreground">
                              Range: {varDef.min ?? "-∞"} to {varDef.max ?? "∞"}
                            </p>
                          )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Optional Variables */}
              {variablesSchema.filter((v) => !v.required).length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-3">
                    Optional Parameters
                  </h4>
                  <div className="space-y-4">
                    {variablesSchema
                      .filter((v) => !v.required)
                      .map((varDef) => (
                        <div key={varDef.name}>
                          <Label htmlFor={varDef.name} className="mb-2 block">
                            <span className="capitalize">
                              {varDef.name.replace(/_/g, " ")}
                            </span>
                          </Label>
                          {renderVariableInput(varDef)}
                          {varDef.description && (
                            <p className="mt-1 text-xs text-muted-foreground dark:text-muted-foreground">
                              {varDef.description}
                            </p>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              if (missingRequired.length > 0) {
                alert(
                  `Please fill in required fields: ${missingRequired
                    .map((v) => v.name)
                    .join(", ")}`
                );
                return;
              }
              onGenerate();
              onOpenChange(false);
            }}
            className="bg-blue-600 hover:bg-blue-700 text-foreground"
            disabled={missingRequired.length > 0}
          >
            Generate Workflow
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
