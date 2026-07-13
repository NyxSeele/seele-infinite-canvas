/**
 * Catch PascalCase JSX tags that are not in scope (missing import / typo).
 * Standalone rule — eslint-plugin-react does not support ESLint 10 yet.
 */
export default {
  meta: {
    type: "problem",
    docs: {
      description: "Disallow undeclared variables in JSX",
    },
    schema: [],
    messages: {
      undefined: "'{{name}}' is not defined.",
    },
  },
  create(context) {
    const sourceCode = context.sourceCode

    function isDeclared(name, node) {
      for (let scope = sourceCode.getScope(node); scope; scope = scope.upper) {
        if (scope.set.has(name)) return true
        // `arguments` / specials
        if (scope.variables.some((v) => v.name === name)) return true
      }
      return false
    }

    function checkIdentifier(node) {
      const name = node.name
      // DOM / intrinsic elements are lowercase; components are PascalCase
      if (!/^[A-Z]/.test(name)) return
      if (isDeclared(name, node)) return
      context.report({ node, messageId: "undefined", data: { name } })
    }

    return {
      JSXOpeningElement(node) {
        if (node.name.type === "JSXIdentifier") {
          checkIdentifier(node.name)
        } else if (node.name.type === "JSXMemberExpression") {
          let obj = node.name
          while (obj.type === "JSXMemberExpression") obj = obj.object
          if (obj.type === "JSXIdentifier") checkIdentifier(obj)
        }
      },
    }
  },
}
