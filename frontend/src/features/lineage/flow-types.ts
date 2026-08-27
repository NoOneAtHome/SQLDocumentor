import type { EdgeTypes, NodeTypes } from '@xyflow/react'
import { ColumnLineageEdge, LineageEdge } from './edges/LineageEdge'
import { ColumnTableNode } from './nodes/ColumnTableNode'
import { ObjectNode } from './nodes/ObjectNode'

/** Module-scope registries (React Flow warns and re-mounts when these are recreated per render). */
export const nodeTypes: NodeTypes = { object: ObjectNode, columnTable: ColumnTableNode }
export const edgeTypes: EdgeTypes = { lineage: LineageEdge, columnLineage: ColumnLineageEdge }
