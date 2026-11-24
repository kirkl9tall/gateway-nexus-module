{{- define "jerumednexus.name" -}}{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}{{- end }}
{{- define "jerumednexus.fullname" -}}
{{- if .Values.fullnameOverride -}}{{ .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else -}}{{ printf "%s-%s" .Release.Name (include "jerumednexus.name" .) | trunc 63 | trimSuffix "-" }}{{- end }}
{{- end }}
{{- define "jerumednexus.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "jerumednexus.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
{{- define "jerumednexus.selectorLabels" -}}
app.kubernetes.io/name: {{ include "jerumednexus.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
{{- define "jerumednexus.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}{{ default (include "jerumednexus.fullname" .) .Values.serviceAccount.name }}{{- else -}}{{ default "default" .Values.serviceAccount.name }}{{- end }}
{{- end }}
