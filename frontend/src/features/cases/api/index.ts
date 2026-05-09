import { casesCrudApi } from './cases'
import { partiesApi } from './parties'
import { logsApi } from './logs'
import { materialsApi } from './materials'

export const caseApi = {
  ...casesCrudApi,
  // Parties
  listParties: partiesApi.list,
  createParty: partiesApi.create,
  updateParty: partiesApi.update,
  deleteParty: partiesApi.delete,
  // Assignments
  listAssignments: partiesApi.listAssignments,
  createAssignment: partiesApi.createAssignment,
  deleteAssignment: partiesApi.deleteAssignment,
  // Grants
  listGrants: partiesApi.listGrants,
  createGrant: partiesApi.createGrant,
  deleteGrant: partiesApi.deleteGrant,
  // Logs
  listLogs: logsApi.list,
  listAllLogs: logsApi.listAll,
  createLog: logsApi.create,
  updateLog: logsApi.update,
  deleteLog: logsApi.delete,
  uploadLogAttachments: logsApi.uploadAttachments,
  // Case Numbers
  listCaseNumbers: logsApi.listCaseNumbers,
  createCaseNumber: logsApi.createCaseNumber,
  updateCaseNumber: logsApi.updateCaseNumber,
  deleteCaseNumber: logsApi.deleteCaseNumber,
  // Materials
  listMaterialCandidates: materialsApi.listCandidates,
  bindMaterials: materialsApi.bind,
  uploadMaterials: materialsApi.upload,
  replaceMaterial: materialsApi.replace,
  renameMaterialGroup: materialsApi.renameGroup,
  deleteMaterial: materialsApi.delete,
  deleteAllMaterials: materialsApi.deleteAll,
  saveMaterialGroupOrder: materialsApi.saveGroupOrder,
  // Templates
  getTemplateBindings: materialsApi.getTemplateBindings,
  bindTemplate: materialsApi.bindTemplate,
  unbindTemplate: materialsApi.unbindTemplate,
  getAvailableTemplates: materialsApi.getAvailableTemplates,
  generateTemplate: materialsApi.generateTemplate,
  unifiedGenerate: materialsApi.unifiedGenerate,
  // Folders
  getFolderBinding: materialsApi.getFolderBinding,
  createFolderBinding: materialsApi.createFolderBinding,
  deleteFolderBinding: materialsApi.deleteFolderBinding,
  browseFolders: materialsApi.browseFolders,
  startFolderScan: materialsApi.startFolderScan,
  getScanStatus: materialsApi.getScanStatus,
  stageScanResults: materialsApi.stageScanResults,
}

export default caseApi
