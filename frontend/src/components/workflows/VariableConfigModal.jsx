/**
 * Variable Configuration Modal
 *
 * ChatGPT-inspired professional modal for configuring workflow variables
 * Uses shadcn Dialog with elegant design and default values
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
import { Settings, Sparkles } from "lucide-react";

export default function VariableConfigModal({
  open,
  onOpenChange,
  template,
  variables,
  onVariablesChange,
  onGenerate,
  isProcessing = false, // NEW: Disable during execution
}) {
  if (!template) return null;

  // Get default value for a variable based on type
  const getDefaultValue = (varDef) => {
    const { type, choices, min, default: defaultVal } = varDef;

    if (defaultVal !== undefined) return defaultVal;

    if (type === "enum" && choices && choices.length > 0) return choices[0];
    if (type === "boolean") return false;
    if (type === "integer" || type === "number")
      return min !== undefined ? min : 0;
    return "";
  };

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
    // Use default value if not set
    const value =
      variables[name] !== undefined &&
      variables[name] !== null &&
      variables[name] !== ""
        ? variables[name]
        : getDefaultValue(varDef);

    if (type === "enum") {
      return (
        <Select
          value={value}
          onValueChange={(val) => handleVariableChange(name, val, type)}
          disabled={isProcessing}
        >
          <SelectTrigger className="focus:ring-primary">
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
        <div className="flex items-center gap-3 p-3 rounded-lg border border-border hover:border-primary/50 transition-colors">
          <Checkbox
            id={name}
            checked={value === true}
            onCheckedChange={(checked) =>
              handleVariableChange(name, checked, type)
            }
            disabled={isProcessing}
          />
          <Label
            htmlFor={name}
            className="text-sm font-medium cursor-pointer flex-1"
          >
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
          disabled={isProcessing}
          className="focus:ring-primary"
        />
      );
    } else {
      return (
        <Input
          type="text"
          value={value}
          onChange={(e) => handleVariableChange(name, e.target.value, type)}
          placeholder={description || `Enter ${name}`}
          disabled={isProcessing}
          className="focus:ring-primary"
        />
      );
    }
  };

  const variablesSchema = template.variables_schema || [];
  const requiredVars = variablesSchema.filter((v) => v.required);

  return (
    <Dialog open={open} onOpenChange={isProcessing ? undefined : onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader className="pb-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Settings className="w-5 h-5 text-primary" />
            </div>
            <div className="flex-1">
              <DialogTitle className="text-xl font-semibold">
                Configure {template.name}
              </DialogTitle>
              <DialogDescription className="text-sm mt-1">
                Customize workflow parameters • Defaults are pre-filled
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-6 py-4 px-1">
          {variablesSchema.length === 0 ? (
            <div className="text-center py-12">
              <Sparkles className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-50" />
              <p className="text-sm text-muted-foreground">
                This workflow has no configurable variables
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Ready to run with default settings
              </p>
            </div>
          ) : (
            <>
              {/* Required Variables */}
              {requiredVars.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                    <span className="w-1 h-4 bg-destructive rounded"></span>
                    Required Fields
                  </h4>
                  <div className="space-y-5">
                    {requiredVars.map((varDef) => (
                      <div key={varDef.name} className="space-y-2">
                        <Label
                          htmlFor={varDef.name}
                          className="text-sm font-medium flex items-center gap-2"
                        >
                          <span className="capitalize">
                            {varDef.name.replace(/_/g, " ")}
                          </span>
                          <span className="text-destructive text-xs">*</span>
                        </Label>
                        {renderVariableInput(varDef)}
                        {varDef.description && (
                          <p className="text-xs text-muted-foreground">
                            {varDef.description}
                          </p>
                        )}
                        {(varDef.type === "integer" ||
                          varDef.type === "number") &&
                          (varDef.min !== undefined ||
                            varDef.max !== undefined) && (
                            <p className="text-xs text-muted-foreground">
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
                  <h4 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                    <span className="w-1 h-4 bg-primary rounded"></span>
                    Optional Parameters
                  </h4>
                  <div className="space-y-5">
                    {variablesSchema
                      .filter((v) => !v.required)
                      .map((varDef) => (
                        <div key={varDef.name} className="space-y-2">
                          <Label
                            htmlFor={varDef.name}
                            className="text-sm font-medium block"
                          >
                            <span className="capitalize">
                              {varDef.name.replace(/_/g, " ")}
                            </span>
                          </Label>
                          {renderVariableInput(varDef)}
                          {varDef.description && (
                            <p className="text-xs text-muted-foreground">
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

        <DialogFooter className="pt-4 border-t border-border">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isProcessing}
          >
            Cancel
          </Button>
          <Button
            onClick={() => {
              // Fill in default values for any missing variables
              const updatedVariables = { ...variables };
              variablesSchema.forEach((varDef) => {
                if (
                  updatedVariables[varDef.name] === undefined ||
                  updatedVariables[varDef.name] === null ||
                  updatedVariables[varDef.name] === ""
                ) {
                  updatedVariables[varDef.name] = getDefaultValue(varDef);
                }
              });
              onVariablesChange(updatedVariables);

              // Proceed with generation
              onGenerate();
              onOpenChange(false);
            }}
            disabled={isProcessing}
            className="bg-primary hover:bg-primary/90 text-primary-foreground gap-2"
          >
            <Sparkles className="w-4 h-4" />
            {isProcessing ? "Running..." : "Generate"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
